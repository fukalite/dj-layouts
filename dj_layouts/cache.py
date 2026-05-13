from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from django.http import HttpRequest


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

    key_func: Callable[[HttpRequest], str]
    timeout: int
    backend: str = "default"
    stale_ttl: int = 0
    refresh_func: Callable[[HttpRequest], str] | None = None

    def make_key(self, panel_name: str, request: HttpRequest) -> str:
        vary = self.key_func(request)
        if vary:
            return f"layouts:panel:{panel_name}:{vary}"
        return f"layouts:panel:{panel_name}"


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_user_id(request: HttpRequest) -> str:
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


def _sitewide_key(request: HttpRequest) -> str:
    """Return an empty vary string so all requests share one cache entry."""
    return ""


def _path_key(request: HttpRequest) -> str:
    """Return the request path as the vary string."""
    return request.path


def _user_per_path_key(request: HttpRequest) -> str:
    """Return ``<user_id>:<path>`` as the vary string."""
    return f"{_get_user_id(request)}:{request.path}"


def _session_key(request: HttpRequest) -> str:
    """
    Return the session key as the vary string.

    Falls back to ``"no-session"`` if the session middleware is not installed
    or the session has not yet been saved.
    """
    session = getattr(request, "session", None)
    session_key = getattr(session, "session_key", None)
    return session_key or "no-session"


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
    return CacheConfig(key_func=_sitewide_key, timeout=timeout, backend=backend)


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
    return CacheConfig(key_func=_path_key, timeout=timeout, backend=backend)


def per_user_per_path(timeout: int, *, backend: str = "default") -> CacheConfig:
    """Cache panel output per user *and* per URL path."""
    return CacheConfig(key_func=_user_per_path_key, timeout=timeout, backend=backend)


def per_session(timeout: int, *, backend: str = "default") -> CacheConfig:
    """
    Cache panel output per session.

    Uses ``request.session.session_key`` as the vary key. Falls back to
    ``"no-session"`` if the session middleware is not installed or the session
    has not yet been created.
    """
    return CacheConfig(key_func=_session_key, timeout=timeout, backend=backend)


def custom(
    key_func: Callable[[HttpRequest], str],
    timeout: int,
    *,
    backend: str = "default",
    stale_ttl: int = 0,
    refresh_func: Callable[[HttpRequest], str] | None = None,
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
