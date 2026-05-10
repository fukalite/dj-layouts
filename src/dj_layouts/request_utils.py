from __future__ import annotations

import copy

from django.http import HttpRequest

from dj_layouts.context import FrozenLayoutContext, LayoutContext


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

    return cloned
