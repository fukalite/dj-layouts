from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from django.http import HttpRequest

from dj_layouts.context import FrozenLayoutContext, LayoutContext


if TYPE_CHECKING:
    from dj_layouts.base import Layout


def mark_request_as_main(request: HttpRequest) -> None:
    """Mark the request as the main (layout-owning) view request."""
    request.layout_role = "main"  # type: ignore[attr-defined]


def mark_request_as_partial(request: HttpRequest, *, partial: bool) -> None:
    """Record whether the request was detected as a partial (no-layout) request."""
    request.is_layout_partial = partial  # type: ignore[attr-defined]


def attach_queues(request: HttpRequest, layout_class: type[Layout]) -> None:
    """Attach fresh, empty layout queues to the request."""
    request.layout_queues = layout_class._create_queues()  # type: ignore[attr-defined]


def clone_request_as_get(request: HttpRequest) -> HttpRequest:
    """
    Return a shallow copy of request suitable for calling a panel view.

    The clone has method=GET, cleared POST/FILES, and layout_role/is_layout_partial
    set appropriately. layout_context is frozen so panels cannot mutate it.
    """
    cloned = copy.copy(request)
    cloned.method = "GET"
    # POST and FILES are lazy-parsed properties on WSGIRequest/ASGIRequest that cache
    # their values in _post/_files. We write directly to __dict__ to bypass the
    # property setter (which doesn't exist) without triggering the lazy parse.
    # This is tested against Django 6.x; if internals change, look here first.
    cloned.__dict__["_post"] = request.POST.__class__()
    cloned.__dict__["_files"] = request.FILES.__class__()
    cloned.__dict__["layout_role"] = "panel"
    cloned.__dict__["is_layout_partial"] = False

    source_ctx = LayoutContext(getattr(request, "layout_context", LayoutContext()))
    cloned.__dict__["layout_context"] = FrozenLayoutContext(source_ctx)

    # Give each panel a fresh, empty set of queues with the same structure
    source_queues: dict = getattr(request, "layout_queues", {})
    cloned.__dict__["layout_queues"] = {
        name: q._new_instance() for name, q in source_queues.items()
    }

    return cloned
