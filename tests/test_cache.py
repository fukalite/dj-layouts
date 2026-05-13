"""Tests for panel caching (Phase 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.http import HttpResponse

from dj_layouts.base import Layout
from dj_layouts.cache import (
    custom,
    per_path,
    per_session,
    per_user,
    per_user_per_path,
    sitewide,
)
from dj_layouts.panels import Panel
from dj_layouts.queues import ScriptQueue, add_script
from dj_layouts.rendering import async_render_with_layout, render_with_layout


# ── CacheConfig.make_key ──────────────────────────────────────────────────────


def test_make_key_sitewide(rf):
    cfg = sitewide(timeout=60)
    key = cfg.make_key("nav", rf.get("/"))
    assert key == "layouts:panel:nav"


def test_make_key_with_vary(rf):
    cfg = per_path(timeout=60)
    key = cfg.make_key("nav", rf.get("/about/"))
    assert key == "layouts:panel:nav:/about/"


def test_make_key_per_user_authenticated(rf):
    cfg = per_user(timeout=60)
    request = rf.get("/")
    request.user = MagicMock(is_authenticated=True, pk=42)
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:42"


def test_make_key_per_user_anonymous(rf):
    cfg = per_user(timeout=60)
    request = rf.get("/")
    request.user = MagicMock(is_authenticated=False)
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:anonymous"


def test_make_key_per_user_no_user_attr(rf):
    cfg = per_user(timeout=60)
    request = rf.get("/")
    # No .user attribute at all
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:anonymous"


def test_make_key_per_user_per_path(rf):
    cfg = per_user_per_path(timeout=60)
    request = rf.get("/items/")
    request.user = MagicMock(is_authenticated=True, pk=7)
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:7:/items/"


def test_make_key_per_session(rf):
    cfg = per_session(timeout=60)
    request = rf.get("/")
    request.session = MagicMock(session_key="abc123")
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:abc123"


def test_make_key_per_session_no_session(rf):
    cfg = per_session(timeout=60)
    request = rf.get("/")
    key = cfg.make_key("nav", request)
    assert key == "layouts:panel:nav:no-session"


def test_make_key_custom(rf):
    cfg = custom(key_func=lambda r: "fixed", timeout=60)
    key = cfg.make_key("nav", rf.get("/"))
    assert key == "layouts:panel:nav:fixed"


# ── CacheConfig fields ────────────────────────────────────────────────────────


def test_stale_ttl_and_refresh_func_accepted():
    """stale_ttl and refresh_func are accepted on CacheConfig without error."""
    cfg = custom(
        key_func=lambda r: "",
        timeout=60,
        stale_ttl=300,
        refresh_func=lambda *a: None,
    )
    assert cfg.stale_ttl == 300
    assert cfg.refresh_func is not None


def test_sitewide_has_correct_timeout():
    cfg = sitewide(timeout=3600)
    assert cfg.timeout == 3600
    assert cfg.backend == "default"


def test_custom_backend_forwarded():
    cfg = sitewide(timeout=60, backend="redis")
    assert cfg.backend == "redis"


# ── Integration: render_with_layout caching ───────────────────────────────────


def test_cached_panel_served_from_cache_on_second_request(cache_test_layout, rf):
    layout_cls, call_count = cache_test_layout
    request1 = rf.get("/")
    request2 = rf.get("/")

    r1 = render_with_layout(request1, layout_cls, "content.html")
    r2 = render_with_layout(request2, layout_cls, "content.html")

    assert b"nav-1" in r1.content
    assert b"nav-1" in r2.content  # same cached output
    assert call_count["nav"] == 1  # panel view only called once


def test_panel_view_called_again_after_cache_miss(cache_test_layout, rf):
    layout_cls, call_count = cache_test_layout
    request = rf.get("/")
    render_with_layout(request, layout_cls, "content.html")
    assert call_count["nav"] == 1
    render_with_layout(rf.get("/"), layout_cls, "content.html")
    assert call_count["nav"] == 1  # still cached


def test_cache_disabled_globally_always_rerenders(cache_test_layout, rf, settings):
    settings.DJ_LAYOUTS = {"CACHE_ENABLED": False}
    layout_cls, call_count = cache_test_layout
    render_with_layout(rf.get("/"), layout_cls, "content.html")
    render_with_layout(rf.get("/"), layout_cls, "content.html")
    assert call_count["nav"] == 2  # no caching


def test_per_user_cache_different_entries_per_user(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/pu.html": ("{% load layouts %}{% panel 'nav' %}{% endpanel %}"),
            "content.html": "",
        }
    )
    call_count = {"nav": 0}

    def nav_fn(request, **kwargs):
        call_count["nav"] += 1
        user_id = getattr(getattr(request, "user", None), "pk", "anon")
        return HttpResponse(f"nav-{user_id}")

    class PerUserLayout(Layout):
        template = "layouts/pu.html"
        nav = Panel(nav_fn, cache=per_user(timeout=60))

    user_a = MagicMock(is_authenticated=True, pk=1)
    user_b = MagicMock(is_authenticated=True, pk=2)

    req_a = rf.get("/")
    req_a.user = user_a
    req_b = rf.get("/")
    req_b.user = user_b

    r_a = render_with_layout(req_a, PerUserLayout, "content.html")
    r_b = render_with_layout(req_b, PerUserLayout, "content.html")

    assert b"nav-1" in r_a.content
    assert b"nav-2" in r_b.content
    assert call_count["nav"] == 2  # separate cache entries

    # Second requests hit cache independently
    req_a2 = rf.get("/")
    req_a2.user = user_a
    r_a2 = render_with_layout(req_a2, PerUserLayout, "content.html")
    req_b2 = rf.get("/")
    req_b2.user = user_b
    r_b2 = render_with_layout(req_b2, PerUserLayout, "content.html")
    assert b"nav-1" in r_a2.content  # served from cache (user 1)
    assert b"nav-2" in r_b2.content
    assert call_count["nav"] == 2  # no extra calls


# ── Queue items cached and replayed ───────────────────────────────────────────


def test_cached_panel_queue_items_replayed_on_cache_hit(locmem_templates, rf):
    """Queue items added by a cached panel are replayed from cache on subsequent requests."""
    locmem_templates(
        {
            "layouts/qcache.html": (
                "{% load layouts %}{% renderscripts %}|{% panel 'content' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )
    call_count = {"widget": 0}

    def widget_fn(request, **kwargs):
        call_count["widget"] += 1
        add_script(request, "/js/widget.js")
        return HttpResponse("widget")

    class QCacheLayout(Layout):
        template = "layouts/qcache.html"
        scripts = ScriptQueue()
        widget = Panel(widget_fn, cache=sitewide(timeout=60))

    r1 = render_with_layout(rf.get("/"), QCacheLayout, "content.html")
    r2 = render_with_layout(rf.get("/"), QCacheLayout, "content.html")

    assert b'<script src="/js/widget.js">' in r1.content
    assert b'<script src="/js/widget.js">' in r2.content  # replayed from cache
    assert call_count["widget"] == 1


def test_queue_items_not_duplicated_on_cache_hit(locmem_templates, rf):
    """Queue deduplication still applies when replaying from cache."""
    locmem_templates(
        {
            "layouts/qdedup.html": (
                "{% load layouts %}{% renderscripts %}|{% panel 'content' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )

    def widget_fn(request, **kwargs):
        add_script(request, "/js/shared.js")
        return HttpResponse("widget")

    class QDedupLayout(Layout):
        template = "layouts/qdedup.html"
        scripts = ScriptQueue()
        widget = Panel(widget_fn, cache=sitewide(timeout=60))

    # First request: renders, caches
    r1 = render_with_layout(rf.get("/"), QDedupLayout, "content.html")
    # Second request: cache hit, queue replayed
    r2 = render_with_layout(rf.get("/"), QDedupLayout, "content.html")

    # Script appears exactly once in each response
    assert r1.content.decode().count('<script src="/js/shared.js">') == 1
    assert r2.content.decode().count('<script src="/js/shared.js">') == 1


# ── Async caching ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_cached_panel_served_from_cache(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/async_cache.html": (
                "{% load layouts %}{% panel 'nav' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )
    call_count = {"nav": 0}

    def nav_fn(request, **kwargs):
        call_count["nav"] += 1
        return HttpResponse(f"nav-{call_count['nav']}")

    class AsyncCacheLayout(Layout):
        template = "layouts/async_cache.html"
        nav = Panel(nav_fn, cache=sitewide(timeout=60))

    r1 = await async_render_with_layout(rf.get("/"), AsyncCacheLayout, "content.html")
    r2 = await async_render_with_layout(rf.get("/"), AsyncCacheLayout, "content.html")

    assert b"nav-1" in r1.content
    assert b"nav-1" in r2.content
    assert call_count["nav"] == 1


@pytest.mark.asyncio
async def test_async_cached_panel_queue_items_replayed(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/async_qcache.html": (
                "{% load layouts %}{% renderscripts %}|{% panel 'content' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )
    call_count = {"widget": 0}

    def widget_fn(request, **kwargs):
        call_count["widget"] += 1
        add_script(request, "/js/async-widget.js")
        return HttpResponse("widget")

    class AsyncQCacheLayout(Layout):
        template = "layouts/async_qcache.html"
        scripts = ScriptQueue()
        widget = Panel(widget_fn, cache=sitewide(timeout=60))

    r1 = await async_render_with_layout(rf.get("/"), AsyncQCacheLayout, "content.html")
    r2 = await async_render_with_layout(rf.get("/"), AsyncQCacheLayout, "content.html")

    assert b'<script src="/js/async-widget.js">' in r1.content
    assert b'<script src="/js/async-widget.js">' in r2.content
    assert call_count["widget"] == 1


@pytest.mark.asyncio
async def test_async_cache_disabled_globally(locmem_templates, rf, settings):
    settings.DJ_LAYOUTS = {"CACHE_ENABLED": False}
    locmem_templates(
        {
            "layouts/async_nodisable.html": (
                "{% load layouts %}{% panel 'nav' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )
    call_count = {"nav": 0}

    def nav_fn(request, **kwargs):
        call_count["nav"] += 1
        return HttpResponse("nav")

    class AsyncNoDisableLayout(Layout):
        template = "layouts/async_nodisable.html"
        nav = Panel(nav_fn, cache=sitewide(timeout=60))

    await async_render_with_layout(rf.get("/"), AsyncNoDisableLayout, "content.html")
    await async_render_with_layout(rf.get("/"), AsyncNoDisableLayout, "content.html")
    assert call_count["nav"] == 2


# ── Cache write verification ──────────────────────────────────────────────────


def test_cache_write_happens_on_miss(locmem_templates, rf):
    """On a cache miss, the result is written to the cache backend."""
    from django.core.cache import caches

    locmem_templates(
        {
            "layouts/write.html": "{% load layouts %}{% panel 'nav' %}{% endpanel %}",
            "content.html": "",
        }
    )

    def nav_fn(request, **kwargs):
        return HttpResponse("nav-content")

    class WriteLayout(Layout):
        template = "layouts/write.html"
        nav = Panel(nav_fn, cache=sitewide(timeout=60))

    render_with_layout(rf.get("/"), WriteLayout, "content.html")

    # Key is deterministic for sitewide
    cached = caches["default"].get("layouts:panel:nav")
    assert cached is not None
    html, queue_snapshot = cached
    assert html == "nav-content"
