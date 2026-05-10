from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable


logger = logging.getLogger(__name__)


# ── CacheConfig dataclass ─────────────────────────────────────────────────────


@dataclass
class CacheConfig:
    """
    Configuration for per-panel caching.

    ``key_func`` receives the request and returns the vary portion of the cache
    key. The full key is ``layouts:panel:<panel_name>:<vary>`` (or just
    ``layouts:panel:<panel_name>`` when the vary portion is empty).

    ``stale_ttl`` and ``refresh_func`` are reserved for future stale-while-
    revalidate support and are silently ignored in v1.
    """

    key_func: Callable[[Any], str]
    timeout: int
    backend: str = "default"
    stale_ttl: int = 0
    refresh_func: Callable[..., Any] | None = None

    def make_key(self, panel_name: str, request: Any) -> str:
        vary = self.key_func(request)
        if vary:
            return f"layouts:panel:{panel_name}:{vary}"
        return f"layouts:panel:{panel_name}"


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_user_id(request: Any) -> str:
    """
    Return a string identifying the current user.

    Falls back to ``"anonymous"`` for unauthenticated users, so that
    ``cache.per_user`` caches work without auth middleware — but note that
    all anonymous users share the same cache entry.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    return str(user.pk)


# ── Shortcut functions ────────────────────────────────────────────────────────


def sitewide(timeout: int, *, backend: str = "default") -> CacheConfig:
    """
    Cache panel output once for all users and all paths.

    Suitable for panels whose content never varies by user, session, or URL —
    e.g. a static footer, a global announcement banner.

    .. warning::
        All users (including anonymous) share the same cache entry. If the
        panel contains user-specific content, use :func:`per_user` instead.
    """
    return CacheConfig(key_func=lambda r: "", timeout=timeout, backend=backend)


def per_user(timeout: int, *, backend: str = "default") -> CacheConfig:
    """
    Cache panel output per authenticated user.

    Uses ``request.user.pk`` as the vary key. Anonymous users all share a
    single ``"anonymous"`` cache entry — document this clearly if your panel
    may render different content for different anonymous sessions.
    """
    return CacheConfig(key_func=_get_user_id, timeout=timeout, backend=backend)


def per_path(timeout: int, *, backend: str = "default") -> CacheConfig:
    """
    Cache panel output per URL path, shared across all users.

    Useful for panels that vary by the current page but not by user — e.g. a
    breadcrumb trail or page-specific sidebar.
    """
    return CacheConfig(key_func=lambda r: r.path, timeout=timeout, backend=backend)


def per_user_per_path(timeout: int, *, backend: str = "default") -> CacheConfig:
    """Cache panel output per user *and* per URL path."""

    def _key(request: Any) -> str:
        return f"{_get_user_id(request)}:{request.path}"

    return CacheConfig(key_func=_key, timeout=timeout, backend=backend)


def per_session(timeout: int, *, backend: str = "default") -> CacheConfig:
    """
    Cache panel output per session.

    Uses ``request.session.session_key`` as the vary key. Falls back to
    ``"no-session"`` if the session middleware is not installed or the session
    has not yet been created.
    """

    def _key(request: Any) -> str:
        session = getattr(request, "session", None)
        key = getattr(session, "session_key", None)
        return key or "no-session"

    return CacheConfig(key_func=_key, timeout=timeout, backend=backend)


def custom(
    key_func: Callable[[Any], str],
    timeout: int,
    *,
    backend: str = "default",
    stale_ttl: int = 0,
    refresh_func: Callable[..., Any] | None = None,
) -> CacheConfig:
    """
    Full control over cache key construction.

    ``key_func(request)`` must return a string that uniquely identifies the
    cache entry for that request. The result is used as the vary portion of the
    full key: ``layouts:panel:<panel_name>:<key_func_result>``.
    """
    return CacheConfig(
        key_func=key_func,
        timeout=timeout,
        backend=backend,
        stale_ttl=stale_ttl,
        refresh_func=refresh_func,
    )
