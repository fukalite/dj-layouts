from __future__ import annotations

from typing import Any


try:
    from wagtail.models import Page  # noqa: F401 — validates Wagtail is installed
except ImportError as exc:
    raise ImportError(
        "dj_layouts.wagtail requires Wagtail to be installed. "
        "Install it with: pip install wagtail"
    ) from exc

from dj_layouts.base import Layout
from dj_layouts.detection import is_partial_request
from dj_layouts.panels import Panel
from dj_layouts.rendering import render_with_layout


class WagtailLayoutMixin:
    """
    Mixin for Wagtail Page subclasses to opt into the layout system.

    Place before Page in the MRO::

        class BlogPage(WagtailLayoutMixin, Page):
            layout_class = BlogLayout
            template = "blog/blog_page.html"  # rendered as the content panel

    In preview mode (``request.is_preview`` is truthy) or for partial requests,
    the standard Wagtail ``serve()`` is called without layout wrapping, so HTMX
    and Wagtail's preview infrastructure work unmodified.
    """

    layout_class: type[Layout] | str | None = None
    layout_panels: dict[str, Panel | None] | None = None

    def serve(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        if getattr(request, "is_preview", False):
            return super().serve(request, *args, **kwargs)  # type: ignore[misc]

        if is_partial_request(request):
            return super().serve(request, *args, **kwargs)  # type: ignore[misc]

        layout_class = self.layout_class
        if layout_class is None:
            from django.core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must define a `layout_class` attribute."
            )

        if isinstance(layout_class, str):
            layout_class = Layout.resolve(layout_class)

        return render_with_layout(
            request,
            layout_class,
            self.get_template(request, *args, **kwargs),  # type: ignore[attr-defined]
            context=self.get_context(request, *args, **kwargs),  # type: ignore[attr-defined]
            panels=self.layout_panels,
        )
