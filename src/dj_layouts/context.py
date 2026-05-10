from __future__ import annotations

from typing import NoReturn


_READ_ONLY_MSG = "layout_context is read-only in panel views"


class LayoutContext(dict):  # type: ignore[type-arg]
    """Mutable layout context dict. Set on request.layout_context for main views."""


class FrozenLayoutContext(dict):  # type: ignore[type-arg]
    """Immutable view of LayoutContext. Set on panel request.layout_context."""

    def _raise(self) -> NoReturn:
        raise TypeError(_READ_ONLY_MSG)

    def __setitem__(self, key: object, value: object) -> None:
        self._raise()

    def __delitem__(self, key: object) -> None:
        self._raise()

    def update(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        self._raise()

    def pop(self, *args: object) -> object:  # type: ignore[override]
        self._raise()

    def clear(self) -> None:
        self._raise()

    def setdefault(self, key: object, default: object = None) -> object:
        self._raise()

    def popitem(self) -> tuple[object, object]:
        self._raise()

    def __ior__(self, other: object) -> FrozenLayoutContext:  # type: ignore[misc]
        self._raise()
