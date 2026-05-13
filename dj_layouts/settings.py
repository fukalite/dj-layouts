from __future__ import annotations

from django.conf import settings
from django.test.signals import setting_changed


DEFAULTS: dict = {
    # None means "follow Django's DEBUG setting". True/False override explicitly.
    "DEBUG_ERRORS": None,
    "CACHE_ENABLED": True,
    "CACHE_BACKEND": "default",
    "PARTIAL_DETECTORS": [],
    "DETECTOR_RAISE_EXCEPTIONS": False,
}


class DjLayoutsSettings:
    """
    Lazy settings proxy for dj-layouts.

    Reads from ``settings.DJ_LAYOUTS`` (a dict) and falls back to ``DEFAULTS``.
    Access any key as an attribute::

        from dj_layouts.settings import dj_layouts_settings

        if dj_layouts_settings.CACHE_ENABLED:
            ...

    In your Django settings::

        DJ_LAYOUTS = {
            "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
            "CACHE_ENABLED": False,   # disable caching in development
        }
    """

    def __getattr__(self, attr: str):
        user_settings: dict = getattr(settings, "DJ_LAYOUTS", {})
        if attr in user_settings:
            return user_settings[attr]
        if attr not in DEFAULTS:
            raise AttributeError(
                f"Invalid dj-layouts setting: DJ_LAYOUTS['{attr}']. "
                f"Available keys: {list(DEFAULTS)}"
            )
        return DEFAULTS[attr]


dj_layouts_settings = DjLayoutsSettings()


def _on_setting_changed(*, setting: str, **kwargs: object) -> None:
    """Invalidate lazy caches when ``DJ_LAYOUTS`` settings change (e.g. in tests)."""
    if setting == "DJ_LAYOUTS":
        from dj_layouts.detection import _reset_detector_cache

        _reset_detector_cache()


setting_changed.connect(_on_setting_changed)
