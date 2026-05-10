from __future__ import annotations

import asyncio
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.http import StreamingHttpResponse
from django.utils.decorators import classonlymethod

from dj_layouts.base import Layout
from dj_layouts.detection import is_partial_request
from dj_layouts.panels import Panel


class LayoutMixin:
    """
    Mixin for Django class-based views that assembles the response inside a Layout.

    Works with both sync and async handler methods (get, post, etc.). The
    ``dispatch`` method is async, so Django treats the view as async. On WSGI
    Django's async-to-sync adapter handles this transparently — you do not need
    ASGI to use ``LayoutMixin``.

    Usage::

        class DashboardView(LayoutMixin, TemplateView):
            layout_class = DefaultLayout       # class or dotted string
            layout_panels = {}                 # optional per-view panel overrides
            template_name = "dashboard/partial.html"

    Partial detection runs the same way as with ``@layout``. Non-200 and
    streaming responses are passed through without layout assembly.
    """

    layout_class: type[Layout] | str | None = None
    layout_panels: dict[str, Panel | None] | None = None

    # Tell Django's as_view() that this view is async.
    view_is_async = True

    @classonlymethod
    def as_view(cls, **initkwargs):
        from asgiref.sync import markcoroutinefunction

        view = super().as_view(**initkwargs)
        # Ensure the returned callable is marked async so Django's URL
        # dispatcher awaits it correctly on both WSGI and ASGI.
        if not asyncio.iscoroutinefunction(view):
            markcoroutinefunction(view)
        return view

    async def dispatch(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        # When acting as a panel, just call through without layout assembly.
        if getattr(request, "layout_role", None) == "panel":
            response = super().dispatch(request, *args, **kwargs)
            if asyncio.iscoroutine(response):
                response = await response
            return response

        if self.layout_class is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must define a `layout_class` attribute."
            )

        resolved_cls = (
            Layout.resolve(self.layout_class)
            if isinstance(self.layout_class, str)
            else self.layout_class
        )

        from dj_layouts.rendering import _async_assemble_layout, _build_layout_context

        request.layout_role = "main"
        layout_ctx = _build_layout_context(resolved_cls, resolved_cls(), request)
        request.layout_queues = resolved_cls._create_queues()

        if is_partial_request(request):
            request.is_layout_partial = True
            response = super().dispatch(request, *args, **kwargs)
            if asyncio.iscoroutine(response):
                response = await response
            # Force-render TemplateResponse even in partial mode.
            if hasattr(response, "render") and not response.is_rendered:
                if asyncio.iscoroutinefunction(response.render):
                    await response.render()
                else:
                    response.render()
            return response

        request.is_layout_partial = False

        response = super().dispatch(request, *args, **kwargs)
        if asyncio.iscoroutine(response):
            response = await response

        # Pass through streaming and non-200 responses unchanged.
        if isinstance(response, StreamingHttpResponse) or response.status_code != 200:
            return response

        # Force-render TemplateResponse (sync or async variant).
        if hasattr(response, "render") and not response.is_rendered:
            if asyncio.iscoroutinefunction(response.render):
                await response.render()
            else:
                response.render()

        content_html = response.content.decode(
            getattr(response, "charset", "utf-8") or "utf-8"
        )

        return await _async_assemble_layout(
            request,
            resolved_cls,
            content_html,
            panels=self.layout_panels,
            _layout_ctx=layout_ctx,
        )
