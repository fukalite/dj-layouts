from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass


# ── Data models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScriptItem:
    src: str | None = None
    inline: str | None = None
    is_async: bool = False
    is_deferred: bool = False
    type: str = ""


@dataclass(frozen=True)
class StyleItem:
    href: str | None = None
    inline: str | None = None
    media: str = ""


# ── Queue base and subtypes ───────────────────────────────────────────────────


class BaseQueue:
    """Ordered, deduplicated accumulator for a single category of content."""

    def __init__(self) -> None:
        self._items: list[Any] = []
        self._seen: set[Any] = set()

    def add(self, item: Any) -> None:
        if item not in self._seen:
            self._seen.add(item)
            self._items.append(item)

    def merge_from(self, other: BaseQueue) -> None:
        """Append all items from *other* that are not already present."""
        for item in other._items:
            self.add(item)

    def _new_instance(self) -> BaseQueue:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError


class ScriptQueue(BaseQueue):
    """Renders collected scripts as ``<script>`` HTML tags."""

    def _new_instance(self) -> ScriptQueue:
        return ScriptQueue()

    def render(self) -> str:
        parts: list[str] = []
        for item in self._items:
            if item.inline is not None:
                parts.append(f"<script>{item.inline}</script>")
                continue

            attr_parts: list[str] = []
            if item.is_async:
                attr_parts.append("async")
            if item.is_deferred:
                attr_parts.append("defer")
            if item.type:
                attr_parts.append(f'type="{item.type}"')
            attrs = (" " + " ".join(attr_parts)) if attr_parts else ""
            parts.append(f'<script{attrs} src="{item.src}"></script>')
        return "\n".join(parts)


class StyleQueue(BaseQueue):
    """Renders collected styles as ``<link>`` or ``<style>`` HTML tags."""

    def _new_instance(self) -> StyleQueue:
        return StyleQueue()

    def render(self) -> str:
        parts: list[str] = []
        for item in self._items:
            if item.inline is not None:
                parts.append(f"<style>{item.inline}</style>")
            else:
                media = f' media="{item.media}"' if item.media else ""
                parts.append(f'<link rel="stylesheet" href="{item.href}"{media}>')
        return "\n".join(parts)


class RenderQueue(BaseQueue):
    """Generic queue. User supplies a template that receives ``items`` in context."""

    def __init__(self, *, template: str) -> None:
        super().__init__()
        self.template = template

    def _new_instance(self) -> RenderQueue:
        return RenderQueue(template=self.template)

    def render(self) -> str:
        from django.template.loader import render_to_string

        return render_to_string(self.template, {"items": self._items})


# ── View-side API ─────────────────────────────────────────────────────────────


def add_script(
    request: Any,
    src: str | None = None,
    *,
    inline: str | None = None,
    is_async: bool = False,
    is_deferred: bool = False,
    type: str = "",
) -> None:
    """Enqueue a script (URL or inline) on the layout's ScriptQueue."""
    item = ScriptItem(
        src=src, inline=inline, is_async=is_async, is_deferred=is_deferred, type=type
    )
    _get_queue(request, "scripts").add(item)


def add_style(
    request: Any,
    href: str | None = None,
    *,
    inline: str | None = None,
    media: str = "",
) -> None:
    """Enqueue a stylesheet (URL or inline) on the layout's StyleQueue."""
    item = StyleItem(href=href, inline=inline, media=media)
    _get_queue(request, "styles").add(item)


def add_to_queue(request: Any, queue_name: str, item: str) -> None:
    """Enqueue a string item on a named RenderQueue."""
    _get_queue(request, queue_name).add(item)


def _get_queue(request: Any, queue_name: str) -> BaseQueue:
    queues: dict[str, BaseQueue] | None = getattr(request, "layout_queues", None)
    if queues is None:
        raise AttributeError(
            "request has no layout_queues; ensure a Layout is being used."
        )
    try:
        return queues[queue_name]
    except KeyError:
        available = list(queues)
        raise KeyError(
            f"No queue named {queue_name!r} registered on this layout. "
            f"Available queues: {available}"
        ) from None
