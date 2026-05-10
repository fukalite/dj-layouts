from __future__ import annotations

import asyncio
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

from dj_layouts.base import Layout
from dj_layouts.context import LayoutContext
from dj_layouts.errors import PanelError, PanelRenderError
from dj_layouts.panels import Panel, async_resolve_panel_source, resolve_panel_source
from dj_layouts.request_utils import clone_request_as_get


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
    request.layout_queues = layout_class._create_queues()

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
    override = getattr(settings, "LAYOUTS_DEBUG_ERRORS", None)
    if override is None:
        return bool(settings.DEBUG)
    return bool(override)


def _merge_panel_queues(request: Any, panel_request: Any) -> None:
    """Merge queue items from a panel request into the layout request, in insertion order."""
    layout_queues: dict = getattr(request, "layout_queues", {})
    panel_queues: dict = getattr(panel_request, "layout_queues", {})
    for name, panel_queue in panel_queues.items():
        if name in layout_queues:
            layout_queues[name].merge_from(panel_queue)


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
    request.layout_queues = layout_class._create_queues()

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
    regardless of completion order. A failing panel calls on_panel_error (or raises
    PanelRenderError in debug mode) without preventing other panels from completing.
    """
    if isinstance(layout_class, str):
        layout_class = Layout.resolve(layout_class)

    layout_instance = layout_class()
    layout_ctx = _layout_ctx or _build_layout_context(
        layout_class, layout_instance, request
    )
    effective_panels = _collect_effective_panels(layout_class, panels)

    # Separate panels that need resolution from panels that are explicitly None.
    # Only non-None panels get a Task — no dummy tasks for empty slots.
    non_none: list[tuple[str, Panel]] = [
        (name, panel) for name, panel in effective_panels.items() if panel is not None
    ]
    # Create all panel requests upfront so we can merge their queues after gather.
    panel_requests = [clone_request_as_get(request) for _ in non_none]
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
        for (_, panel), panel_request in zip(non_none, panel_requests)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    rendered_panels: dict[str, str] = {"content": content_html}
    # Pre-fill None panels
    for panel_name, panel in effective_panels.items():
        if panel is None:
            rendered_panels[panel_name] = ""
    # Merge gathered results and queues in definition order
    for (panel_name, panel), result, panel_request in zip(
        non_none, results, panel_requests, strict=True
    ):
        if isinstance(result, Exception):
            rendered_panels[panel_name] = _handle_panel_error(
                layout_instance, request, panel_name, panel.source, result
            )
        else:
            rendered_panels[panel_name] = result  # type: ignore[assignment]
        _merge_panel_queues(request, panel_request)

    return _render_layout_template(
        layout_instance, request, rendered_panels, layout_ctx
    )
