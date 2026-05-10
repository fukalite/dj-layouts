from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


logger = logging.getLogger(__name__)

_loaded_detectors: list | None = None


def never_detector(request: Any) -> bool:
    """Default detector — always returns False (layout always applied)."""
    return False


def htmx_detector(request: Any) -> bool:
    """Returns True if the request carries the HX-Request: true header (HTMX)."""
    return request.headers.get("HX-Request") == "true"


def query_param_detector(request: Any) -> bool:
    """Returns True if ?_partial=1 is present in the query string."""
    return request.GET.get("_partial") == "1"


def _get_detectors() -> list:
    global _loaded_detectors
    if _loaded_detectors is None:
        _loaded_detectors = _load_detectors()
    return _loaded_detectors


def _load_detectors() -> list:
    paths = getattr(settings, "LAYOUTS_PARTIAL_DETECTORS", [])
    detectors = []
    for path in paths:
        try:
            detector = import_string(path)
        except ImportError as exc:
            raise ImproperlyConfigured(
                f"LAYOUTS_PARTIAL_DETECTORS: could not import {path!r}. {exc}"
            ) from exc
        detectors.append(detector)
    return detectors


def _reset_detector_cache() -> None:
    """Reset the loaded-detector cache (for tests and settings overrides)."""
    global _loaded_detectors
    _loaded_detectors = None


def is_partial_request(request: Any) -> bool:
    """
    Return True if any configured detector identifies this as a partial request.

    Detectors are loaded lazily from LAYOUTS_PARTIAL_DETECTORS on first call.
    If a detector raises an exception it is logged at WARNING level and treated
    as False (layout still assembled). Set LAYOUTS_DETECTOR_RAISE_EXCEPTIONS = True
    to re-raise instead.
    """
    raise_on_error = bool(getattr(settings, "LAYOUTS_DETECTOR_RAISE_EXCEPTIONS", False))

    for detector in _get_detectors():
        try:
            if detector(request):
                return True
        except Exception:
            if raise_on_error:
                raise
            logger.warning(
                "Detector %r raised an exception; treating as False.",
                detector,
                exc_info=True,
            )
    return False
