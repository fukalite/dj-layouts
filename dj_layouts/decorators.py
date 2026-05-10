from __future__ import annotations

import asyncio
import functools
from typing import Any

from django.http import HttpResponseForbidden, StreamingHttpResponse

from dj_layouts.base import Layout
from dj_layouts.panels import Panel


_PANEL_ONLY_MARKER = "_is_panel_only"


def layout(
    layout_class: type[Layout] | str,
    *,
    panels: dict[str, Panel | None] | None = None,
) -> Any:
    """
    Decorator that wraps a view to render it inside a Layout.

    @layout(MyLayout)
    @layout("myapp.MyLayout")
    @layout(MyLayout, panels={"sidebar": Panel(...)})

    layout_context is built and set on request BEFORE the wrapped view executes,
    so the view and its templates can access request.layout_context.

    Non-HTML responses (redirects, error responses, streaming) are passed through
    unchanged without layout wrapping.
    """

    def decorator(view_func: Any) -> Any:
        if getattr(view_func, _PANEL_ONLY_MARKER, False):
            raise TypeError(
                f"Cannot apply @layout to a @panel_only view ({view_func.__name__!r}). "
                "These decorators are mutually exclusive."
            )

        @functools.wraps(view_func)
        def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            # No-op when already in a panel role
            if getattr(request, "layout_role", None) == "panel":
                return view_func(request, *args, **kwargs)

            request.layout_role = "main"
            request.is_layout_partial = False

            # Resolve layout class and build layout_context BEFORE calling the view
            # so the view and its templates can read request.layout_context.
            from dj_layouts.rendering import _assemble_layout, _build_layout_context

            resolved_cls = (
                Layout.resolve(layout_class)
                if isinstance(layout_class, str)
                else layout_class
            )
            layout_ctx = _build_layout_context(resolved_cls, resolved_cls(), request)
            # Attach queues before the view runs so it can call add_script / add_style
            request.layout_queues = resolved_cls._create_queues()

            response = view_func(request, *args, **kwargs)

            # Pass through streaming responses and non-200 responses (redirects,
            # error pages, etc.) without layout wrapping.
            if (
                isinstance(response, StreamingHttpResponse)
                or response.status_code != 200
            ):
                return response

            # Force-render TemplateResponse before handing to layout engine
            if hasattr(response, "render") and not response.is_rendered:
                response.render()

            content_html = response.content.decode(
                getattr(response, "charset", "utf-8") or "utf-8"
            )

            return _assemble_layout(
                request,
                resolved_cls,
                content_html,
                panels=panels,
                _layout_ctx=layout_ctx,
            )

        return wrapper

    return decorator


def panel_only(view_func: Any) -> Any:
    """
    Decorator that restricts a view to panel-role requests only.

    Returns 403 if called directly (layout_role != "panel").
    Raises TypeError at decoration time if combined with @layout.
    """

    @functools.wraps(view_func)
    def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
        if getattr(request, "layout_role", None) == "panel":
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden()

    setattr(wrapper, _PANEL_ONLY_MARKER, True)
    return wrapper


def async_layout(
    layout_class: type[Layout] | str,
    *,
    panels: dict[str, Panel | None] | None = None,
) -> Any:
    """
    Async decorator that wraps an async view to render it inside a Layout.

    Panels run concurrently via asyncio.gather. Use this on ASGI projects
    with async views. For sync views on WSGI projects, use @layout instead.

    @async_layout(MyLayout)
    async def my_view(request): ...

    layout_context is set on request BEFORE the wrapped view executes.
    Non-200 and StreamingHttpResponse responses are passed through unchanged.
    """

    def decorator(view_func: Any) -> Any:
        if getattr(view_func, _PANEL_ONLY_MARKER, False):
            raise TypeError(
                f"Cannot apply @async_layout to a @panel_only view ({view_func.__name__!r}). "
                "These decorators are mutually exclusive."
            )
        if not asyncio.iscoroutinefunction(view_func):
            raise TypeError(
                f"@async_layout requires an async view function; {view_func.__name__!r} is sync. "
                "Use @layout for sync views."
            )

        @functools.wraps(view_func)
        async def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            if getattr(request, "layout_role", None) == "panel":
                return await view_func(request, *args, **kwargs)

            request.layout_role = "main"
            request.is_layout_partial = False

            from dj_layouts.rendering import (
                _async_assemble_layout,
                _build_layout_context,
            )

            resolved_cls = (
                Layout.resolve(layout_class)
                if isinstance(layout_class, str)
                else layout_class
            )
            layout_ctx = _build_layout_context(resolved_cls, resolved_cls(), request)
            # Attach queues before the view runs so it can call add_script / add_style
            request.layout_queues = resolved_cls._create_queues()

            response = await view_func(request, *args, **kwargs)

            if (
                isinstance(response, StreamingHttpResponse)
                or response.status_code != 200
            ):
                return response

            if hasattr(response, "render") and not response.is_rendered:
                response.render()

            content_html = response.content.decode(
                getattr(response, "charset", "utf-8") or "utf-8"
            )
            return await _async_assemble_layout(
                request,
                resolved_cls,
                content_html,
                panels=panels,
                _layout_ctx=layout_ctx,
            )

        return wrapper

    return decorator
