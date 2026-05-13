from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse
from django.template.loader import render_to_string

from dj_layouts.base import Layout
from dj_layouts.context import LayoutContext
from dj_layouts.errors import PanelError, PanelRenderError
from dj_layouts.panels import Panel, async_resolve_panel_source, resolve_panel_source
from dj_layouts.services.requests import attach_queues, clone_request_as_get
from dj_layouts.settings import dj_layouts_settings


logger = logging.getLogger(__name__)


def render_with_layout(
    request: Any,
    layout_class: type[Layout] | str,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    panels: dict[str, Panel | None] | None = None,
) -> HttpResponse:
    """
    Render template_name as the 'content' panel, assemble all other panels,
    then render the layout template and return a full-page HttpResponse.

    layout_context is set on request BEFORE the main template renders, so
    templates can access request.layout_context if needed.
    """
    if isinstance(layout_class, str):
        layout_class = Layout.resolve(layout_class)

    layout_instance = layout_class()
    layout_ctx = _build_layout_context(layout_class, layout_instance, request)

    # Attach fresh queues before rendering content so the main view can enqueue items
    attach_queues(request, layout_class)

    content_html = render_to_string(template_name, context or {}, request=request)
    return _assemble_layout(
        request, layout_class, content_html, panels=panels, _layout_ctx=layout_ctx
    )


def _assemble_layout(
    request: Any,
    layout_class: type[Layout] | str,
    content_html: str,
    *,
    panels: dict[str, Panel | None] | None = None,
    _layout_ctx: LayoutContext | None = None,
) -> HttpResponse:
    """
    Assemble all panels sequentially and render the layout template.

    Each panel source receives a cloned GET request so panel views cannot
    see POST data and always have layout_role='panel'.
    Panels with a CacheConfig are served from cache when available; on a miss
    both the rendered HTML and the panel's queue items are cached together.
    """
    if isinstance(layout_class, str):
        layout_class = Layout.resolve(layout_class)

    layout_instance = layout_class()
    layout_ctx = _layout_ctx or _build_layout_context(
        layout_class, layout_instance, request
    )
    effective_panels = _collect_effective_panels(layout_class, panels)

    rendered_panels: dict[str, str] = {"content": content_html}

    for panel_name, panel in effective_panels.items():
        if panel is None:
            rendered_panels[panel_name] = ""
            continue

        # ── Cache check ───────────────────────────────────────────────────────
        cache_cfg = panel.cache
        cache_key: str | None = None
        if cache_cfg is not None and _cache_enabled():
            cache_key = cache_cfg.make_key(panel_name, request)
            backend = caches[cache_cfg.backend]
            cached = backend.get(cache_key)
            if cached is not None:
                logger.debug("Panel cache hit: %r (key=%s)", panel_name, cache_key)
                html, queue_snapshot = cached
                rendered_panels[panel_name] = html
                _replay_queue_snapshot(request, queue_snapshot)
                continue
            logger.debug("Panel cache miss: %r (key=%s)", panel_name, cache_key)

        # ── Render ────────────────────────────────────────────────────────────
        panel_request = clone_request_as_get(request)
        try:
            html = resolve_panel_source(
                panel_request,
                panel.source,
                _source_kind=panel._source_kind,
                _join=panel.join,
                **panel.context,
            )
            rendered_panels[panel_name] = html
        except Exception as exc:
            rendered_panels[panel_name] = _handle_panel_error(
                layout_instance, request, panel_name, panel.source, exc
            )
            _merge_panel_queues(request, panel_request)
            continue

        # ── Cache write ───────────────────────────────────────────────────────
        if cache_key is not None:
            queue_snapshot = _snapshot_queues(panel_request)
            backend = caches[cache_cfg.backend]  # type: ignore[union-attr]
            backend.set(cache_key, (html, queue_snapshot), timeout=cache_cfg.timeout)

        _merge_panel_queues(request, panel_request)

    return _render_layout_template(
        layout_instance, request, rendered_panels, layout_ctx
    )


def _collect_effective_panels(
    layout_class: type[Layout],
    overrides: dict[str, Panel | None] | None,
) -> dict[str, Panel | None]:
    """Merge class-level panel definitions with per-call overrides."""
    effective: dict[str, Panel | None] = dict(layout_class._panels)
    if overrides:
        effective.update(overrides)
    return effective


def _handle_panel_error(
    layout_instance: Layout,
    request: Any,
    panel_name: str,
    source: Any,
    exc: Exception,
) -> str:
    """Convert a panel exception into fallback HTML (or re-raise in debug mode)."""
    error = PanelError.from_exc(panel_name, source, exc)
    if _debug_errors():
        raise PanelRenderError(error) from exc
    return layout_instance.on_panel_error(request, error) or ""


def _render_layout_template(
    layout_instance: Layout,
    request: Any,
    rendered_panels: dict[str, str],
    layout_ctx: LayoutContext,
) -> HttpResponse:
    """Render the layout template with all assembled panel outputs."""
    layout_template = layout_instance.get_template(request)
    full_html = render_to_string(
        layout_template,
        {"_panels": rendered_panels, **layout_ctx, "request": request},
    )
    return HttpResponse(full_html)


def _build_layout_context(
    layout_class: type[Layout],
    layout_instance: Layout,
    request: Any,
) -> LayoutContext:
    """Build and set the mutable layout context on the request."""
    ctx = LayoutContext(layout_class.layout_context_defaults)
    ctx.update(layout_instance.get_layout_context(request))
    request.layout_context = ctx
    return ctx


def _debug_errors() -> bool:
    """Return True if panel errors should raise PanelRenderError."""
    override = dj_layouts_settings.DEBUG_ERRORS
    if override is None:
        return bool(settings.DEBUG)
    return bool(override)


def _cache_enabled() -> bool:
    """Return True unless CACHE_ENABLED is explicitly False."""
    return bool(dj_layouts_settings.CACHE_ENABLED)


def _merge_panel_queues(request: Any, panel_request: Any) -> None:
    """Merge queue items from a panel request into the layout request, in insertion order."""
    layout_queues: dict = getattr(request, "layout_queues", {})
    panel_queues: dict = getattr(panel_request, "layout_queues", {})
    for name, panel_queue in panel_queues.items():
        if name in layout_queues:
            layout_queues[name].merge_from(panel_queue)


def _snapshot_queues(panel_request: Any) -> dict[str, list]:
    """Capture a panel's queue items as plain lists for cache storage."""
    return {
        name: list(q._items)
        for name, q in getattr(panel_request, "layout_queues", {}).items()
    }


def _replay_queue_snapshot(request: Any, snapshot: dict[str, list]) -> None:
    """Replay cached queue items into the main request's queues."""
    layout_queues: dict = getattr(request, "layout_queues", {})
    for name, items in snapshot.items():
        if name not in layout_queues:
            continue
        for item in items:
            layout_queues[name].add(item)


# ── Async assembly ────────────────────────────────────────────────────────────


async def async_render_with_layout(
    request: Any,
    layout_class: type[Layout] | str,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    panels: dict[str, Panel | None] | None = None,
) -> HttpResponse:
    """
    Async equivalent of render_with_layout. Panels render concurrently via asyncio.gather.

    layout_context is set on request BEFORE the main template renders.
    Use this with @async_layout or in async views on ASGI projects.
    Sync panel callables are automatically wrapped with sync_to_async.
    """
    if isinstance(layout_class, str):
        layout_class = Layout.resolve(layout_class)

    layout_instance = layout_class()
    layout_ctx = _build_layout_context(layout_class, layout_instance, request)

    # Attach fresh queues before rendering content so the main view can enqueue items.
    # Queue items from the content view will precede panel contributions — panels are
    # merged in definition order after asyncio.gather completes.
    attach_queues(request, layout_class)

    content_html = render_to_string(template_name, context or {}, request=request)
    return await _async_assemble_layout(
        request, layout_class, content_html, panels=panels, _layout_ctx=layout_ctx
    )


async def _async_assemble_layout(
    request: Any,
    layout_class: type[Layout] | str,
    content_html: str,
    *,
    panels: dict[str, Panel | None] | None = None,
    _layout_ctx: LayoutContext | None = None,
) -> HttpResponse:
    """
    Assemble all panels concurrently via asyncio.gather, then render the layout template.

    Panels run concurrently in definition order; results are assembled in definition order
    regardless of completion order. Panels with a CacheConfig are checked before task
    creation — cache hits skip rendering entirely. Both HTML and queue items are cached
    together so scripts/styles added by a cached panel are correctly replayed on hit.

    A failing panel calls on_panel_error (or raises PanelRenderError in debug mode)
    without preventing other panels from completing.
    """
    if isinstance(layout_class, str):
        layout_class = Layout.resolve(layout_class)

    layout_instance = layout_class()
    layout_ctx = _layout_ctx or _build_layout_context(
        layout_class, layout_instance, request
    )
    effective_panels = _collect_effective_panels(layout_class, panels)

    # ── Cache check (sequential, in definition order) ─────────────────────────
    # Panels with a cache hit are stored here; misses (and uncached) go to tasks.
    non_none: list[tuple[str, Panel]] = [
        (name, cast(Panel, panel))
        for name, panel in effective_panels.items()
        if panel is not None
    ]

    cache_hits: dict[str, tuple[str, dict]] = {}  # panel_name -> (html, queue_snapshot)
    needs_render: list[
        tuple[str, Panel, str | None]
    ] = []  # (name, panel, cache_key|None)

    for panel_name, panel in non_none:
        cache_cfg = panel.cache
        cache_key = None
        if cache_cfg is not None and _cache_enabled():
            cache_key = cache_cfg.make_key(panel_name, request)
            backend = caches[cache_cfg.backend]
            cached = await backend.aget(cache_key)
            if cached is not None:
                logger.debug("Panel cache hit: %r (key=%s)", panel_name, cache_key)
                cache_hits[panel_name] = cached
                continue
            logger.debug("Panel cache miss: %r (key=%s)", panel_name, cache_key)
        needs_render.append((panel_name, panel, cache_key))

    # ── Concurrent rendering for cache misses ─────────────────────────────────
    panel_requests = [clone_request_as_get(request) for _ in needs_render]
    tasks = [
        asyncio.create_task(
            async_resolve_panel_source(
                panel_request,
                panel.source,
                _source_kind=panel._source_kind,
                _join=panel.join,
                **panel.context,
            )
        )
        for (_, panel, _), panel_request in zip(needs_render, panel_requests)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── Assemble in definition order ──────────────────────────────────────────
    rendered_panels: dict[str, str] = {"content": content_html}
    for panel_name, panel_or_none in effective_panels.items():
        if panel_or_none is None:
            rendered_panels[panel_name] = ""

    render_idx = 0
    for panel_name, panel in non_none:
        if panel_name in cache_hits:
            html, queue_snapshot = cache_hits[panel_name]
            rendered_panels[panel_name] = html
            _replay_queue_snapshot(request, queue_snapshot)
            continue

        _, _, cache_key = needs_render[render_idx]
        panel_request = panel_requests[render_idx]
        result = results[render_idx]
        render_idx += 1

        if isinstance(result, Exception):
            rendered_panels[panel_name] = _handle_panel_error(
                layout_instance, request, panel_name, panel.source, result
            )
            _merge_panel_queues(request, panel_request)
            continue

        html = result  # type: ignore[assignment]
        rendered_panels[panel_name] = html

        # Cache write (HTML + queue snapshot together)
        if cache_key is not None:
            queue_snapshot = _snapshot_queues(panel_request)
            cache_cfg = panel.cache  # type: ignore[union-attr]
            backend = caches[cache_cfg.backend]
            await backend.aset(
                cache_key, (html, queue_snapshot), timeout=cache_cfg.timeout
            )

        _merge_panel_queues(request, panel_request)

    return _render_layout_template(
        layout_instance, request, rendered_panels, layout_ctx
    )
