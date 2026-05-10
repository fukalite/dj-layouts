from __future__ import annotations

import asyncio
from typing import Any, Literal

from django.http import HttpResponse
from django.urls import resolve, reverse


_SENTINEL = object()

_SourceKind = Literal["auto", "url_name", "literal"]


class Panel:
    """
    Descriptor-style config for a named region in a Layout.

    Source can be specified three ways — pick exactly one:

      Panel("app:view_name")           positional, contains ":" → resolved as URL name
      Panel("plain text / html")       positional, no ":" → returned as literal content
      Panel(url_name="home")           explicit URL name; reverse() is always called,
                                       so non-namespaced names work without needing ":"
      Panel(literal="text:with:colons")  explicit literal; never passed to reverse()

    Keyword args:
      context — extra kwargs forwarded to the source callable/view
      cache   — CacheConfig (future phases)
      join    — separator when source is a list
    """

    _source_kind: _SourceKind

    def __init__(
        self,
        source: Any = _SENTINEL,
        *,
        url_name: str | None = None,
        literal: str | None = None,
        context: dict[str, Any] | None = None,
        cache: Any = None,
        join: str = "",
    ) -> None:
        given = sum(
            [source is not _SENTINEL, url_name is not None, literal is not None]
        )
        if given > 1:
            raise TypeError(
                "Panel accepts at most one of: positional source, url_name=, literal="
            )

        if url_name is not None:
            self.source: Any = url_name
            self._source_kind = "url_name"
        elif literal is not None:
            self.source = literal
            self._source_kind = "literal"
        else:
            self.source = None if source is _SENTINEL else source
            self._source_kind = "auto"

        self.context: dict[str, Any] = context or {}
        self.cache = cache
        self.join = join


def resolve_panel_source(
    request: Any,
    source: Any = _SENTINEL,
    *,
    url_name: str | None = None,
    literal: str | None = None,
    _source_kind: _SourceKind = "auto",
    _join: str = "",
    **extra_context: Any,
) -> str:
    """
    Resolve a single panel source to an HTML string.

    Can be called with a positional source or with explicit url_name=/literal= kwargs
    (same convention as Panel). _source_kind and _join are used internally by the
    assembly loop to forward the kind and join separator recorded on a Panel instance.

    Handles: URL name (str with ":"), callable, plain string, list, None.
    Raises NoReverseMatch / TypeError on failure (callers decide how to handle it).
    """
    given = sum([source is not _SENTINEL, url_name is not None, literal is not None])
    if given > 1:
        raise TypeError(
            "resolve_panel_source accepts at most one of: positional source, url_name=, literal="
        )

    if url_name is not None:
        return _call_url(request, reverse(url_name), extra_context)

    if literal is not None:
        return literal

    actual_source = None if source is _SENTINEL else source

    if actual_source is None:
        return ""

    if isinstance(actual_source, list):
        parts: list[str] = []
        for item in actual_source:
            parts.append(resolve_panel_source(request, item, **extra_context))
        return _join.join(parts)

    if isinstance(actual_source, str):
        return _resolve_string_source(
            request, actual_source, extra_context, _source_kind
        )

    if callable(actual_source):
        return _resolve_callable_source(request, actual_source, extra_context)

    raise TypeError(f"Unsupported panel source type: {type(actual_source)!r}")


def _resolve_string_source(
    request: Any, source: str, context: dict[str, Any], kind: _SourceKind
) -> str:
    """
    Resolve a string panel source according to its kind:

    - "literal"  → always returned as-is
    - "url_name" → always passed to reverse() (NoReverseMatch propagates)
    - "auto"     → ":" present → reverse() (NoReverseMatch propagates, no fallback)
                   no ":"      → returned as literal content
    """
    if kind == "literal":
        return source

    if kind == "url_name" or ":" in source:
        return _call_url(request, reverse(source), context)

    # "auto" without ":" — treat as literal content
    return source


def _resolve_callable_source(request: Any, fn: Any, context: dict[str, Any]) -> str:
    result = fn(request, **context)
    return _extract_str(result)


def _call_url(request: Any, url: str, context: dict[str, Any]) -> str:
    """
    Call the view at `url` with `request` and `context`.

    `context` is merged on top of URL-captured kwargs, so panel context takes
    precedence over URL parameters. This is intentional: it lets callers supply
    values that override what the URL captured (e.g. Panel(source, context={"pk": 5})).
    If you want URL parameters to win, do not duplicate them in Panel.context.
    """
    match = resolve(url)
    response = match.func(request, *match.args, **{**match.kwargs, **context})
    return _extract_str(response)


def _extract_str(result: Any) -> str:
    if isinstance(result, HttpResponse):
        return result.content.decode(result.charset or "utf-8")
    if isinstance(result, str):
        return result
    raise TypeError(
        f"Panel source returned unsupported type {type(result)!r}; expected HttpResponse or str."
    )


# ── Async panel resolution ────────────────────────────────────────────────────


async def async_resolve_panel_source(
    request: Any,
    source: Any = _SENTINEL,
    *,
    url_name: str | None = None,
    literal: str | None = None,
    _source_kind: _SourceKind = "auto",
    _join: str = "",
    **extra_context: Any,
) -> str:
    """
    Async equivalent of resolve_panel_source.

    Sync callables and sync URL-resolved views are automatically wrapped with
    sync_to_async. Native async callables are awaited directly.
    Same source/kwarg conventions as resolve_panel_source.
    """
    given = sum([source is not _SENTINEL, url_name is not None, literal is not None])
    if given > 1:
        raise TypeError(
            "async_resolve_panel_source accepts at most one of: positional source, url_name=, literal="
        )

    if url_name is not None:
        return await _async_call_url(request, reverse(url_name), extra_context)

    if literal is not None:
        return literal

    actual_source = None if source is _SENTINEL else source

    if actual_source is None:
        return ""

    if isinstance(actual_source, list):
        tasks = [
            async_resolve_panel_source(request, item, **extra_context)
            for item in actual_source
        ]
        parts: list[str] = list(await asyncio.gather(*tasks))
        return _join.join(parts)

    if isinstance(actual_source, str):
        return await _async_resolve_string_source(
            request, actual_source, extra_context, _source_kind
        )

    if callable(actual_source):
        if asyncio.iscoroutinefunction(actual_source):
            result = await actual_source(request, **extra_context)
        else:
            from asgiref.sync import sync_to_async

            result = await sync_to_async(actual_source)(request, **extra_context)
        return _extract_str(result)

    raise TypeError(f"Unsupported panel source type: {type(actual_source)!r}")


async def _async_resolve_string_source(
    request: Any, source: str, context: dict[str, Any], kind: _SourceKind
) -> str:
    if kind == "literal":
        return source
    if kind == "url_name" or ":" in source:
        return await _async_call_url(request, reverse(source), context)
    return source


async def _async_call_url(request: Any, url: str, context: dict[str, Any]) -> str:
    """
    Async equivalent of _call_url. Wraps sync views with sync_to_async.

    Context takes precedence over URL-captured kwargs (same as sync path).
    """
    match = resolve(url)
    kwargs = {**match.kwargs, **context}
    if asyncio.iscoroutinefunction(match.func):
        result = await match.func(request, *match.args, **kwargs)
    else:
        from asgiref.sync import sync_to_async

        result = await sync_to_async(match.func)(request, *match.args, **kwargs)
    return _extract_str(result)
