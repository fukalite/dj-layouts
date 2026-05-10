from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from dj_layouts.errors import PanelError


_registry: dict[str, type[Layout]] = {}

_SENTINEL = object()

logger = logging.getLogger(__name__)


class Layout:
    """Base class for all layouts. Subclasses are auto-registered."""

    template: str = _SENTINEL  # type: ignore[assignment]
    error_template: str = "layouts/error.html"
    layout_context_defaults: dict[str, Any] = {}
    _panels: dict[str, Any]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Validate that concrete subclasses declare a template.
        # __init_subclass__ is never called for Layout itself, only for subclasses,
        # so no base-class guard is needed here.
        if not hasattr(cls, "template") or cls.template is _SENTINEL:  # type: ignore[comparison-overlap]
            raise TypeError(f"{cls.__name__} must define a 'template' class attribute.")

        # Collect Panel descriptors defined directly on this class
        collected: dict[str, Any] = {
            attr: val for attr, val in vars(cls).items() if _is_panel(val)
        }
        # Inherit panels from Layout parent classes (direct definition wins)
        for base in cls.__mro__[1:]:
            if base is Layout or not issubclass(base, Layout):
                continue
            for attr, val in getattr(base, "_panels", {}).items():
                collected.setdefault(attr, val)
        cls._panels = collected

        # Register by "<app_label>.<ClassName>"
        app_label = cls.__module__.split(".")[0]
        key = f"{app_label}.{cls.__name__}"
        _registry[key] = cls

    @classmethod
    def resolve(cls, dotted: str) -> type[Layout]:
        """Resolve a dotted string like 'myapp.MyLayout' to the Layout class."""
        try:
            return _registry[dotted]
        except KeyError:
            raise KeyError(
                f"No layout registered as '{dotted}'. Available: {list(_registry)}"
            ) from None

    def get_layout_context(self, request: Any) -> dict[str, Any]:
        """Return extra context merged into layout_context. Override as needed."""
        return {}

    def get_template(self, request: Any) -> str:
        """Return the template path. Override for dynamic template selection."""
        return self.template

    def on_panel_error(self, request: Any, error: PanelError) -> str:
        """
        Handle a panel rendering failure.

        In DEBUG mode this method is bypassed — PanelRenderError is raised directly
        by the assembly engine (controlled via the LAYOUTS_DEBUG_ERRORS setting).

        In production (and when LAYOUTS_DEBUG_ERRORS=False locally), this method is
        called. It logs the error and renders error_template so the page can still
        load with a graceful fallback. Override error_template on the Layout class to
        use a custom template, or override this method entirely for custom handling.

        Returns '' if error_template itself fails to render.
        """
        logger.error(
            "Panel '%s' failed: %s\n%s",
            error.panel_name,
            error.exception,
            error.traceback_str,
        )
        from django.template.loader import render_to_string

        try:
            return render_to_string(self.error_template, {"error": error})
        except Exception:
            return ""


def _is_panel(obj: Any) -> bool:
    from dj_layouts.panels import (
        Panel,  # late import avoids circular import at module load
    )

    return isinstance(obj, Panel)
