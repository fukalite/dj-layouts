from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import override_settings

from dj_layouts.base import Layout
from dj_layouts.decorators import async_layout, layout
from dj_layouts.detection import htmx_detector


class TestLayoutOne(Layout):
    template = "layouts/one.html"


class TestLayoutTwo(Layout):
    template = "layouts/two.html"


# ── Detector Tests ────────────────────────────────────────────────────────────


def test_htmx_detector_smart_routing_disabled(rf):
    """When HTMX_SMART_ROUTING is False, it falls back to standard behavior."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    # Even with a mismatch, should return True because smart routing is False
    request._dj_layouts_target_class = TestLayoutOne
    request.COOKIES["dj_layout_current"] = "TestLayoutTwo"

    assert htmx_detector(request) is True


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_COOKIE_NAME": "dj_layout_current",
    }
)
def test_htmx_detector_smart_routing_no_target_class(rf):
    """If no target layout is attached, return True (fallback)."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    assert htmx_detector(request) is True


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_COOKIE_NAME": "dj_layout_current",
    }
)
def test_htmx_detector_smart_routing_force_full(rf):
    """If force_full escape hatch is set, return False (forcing full layout)."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request._dj_layouts_target_class = TestLayoutOne
    request.dj_layouts_force_full = True

    assert htmx_detector(request) is False


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_COOKIE_NAME": "dj_layout_current",
    }
)
def test_htmx_detector_smart_routing_cookie_match(rf):
    """If current layout in cookie matches target layout, return True (partial)."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request._dj_layouts_target_class = TestLayoutOne
    request.COOKIES["dj_layout_current"] = "TestLayoutOne"

    assert htmx_detector(request) is True


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_COOKIE_NAME": "dj_layout_current",
    }
)
def test_htmx_detector_smart_routing_cookie_mismatch(rf):
    """If current layout in cookie differs from target layout, return False (full)."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request._dj_layouts_target_class = TestLayoutOne
    request.COOKIES["dj_layout_current"] = "TestLayoutTwo"

    assert htmx_detector(request) is False


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_COOKIE_NAME": "dj_layout_current",
    }
)
def test_htmx_detector_smart_routing_no_cookie(rf):
    """If cookie is absent, return False (full)."""
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request._dj_layouts_target_class = TestLayoutOne

    assert htmx_detector(request) is False


# ── Decorator Attribute Tests ──────────────────────────────────────────────────


def test_decorator_layout_class_attribute():
    """Verify that layout_class attribute is attached to wrappers."""

    @layout(TestLayoutOne)
    def my_view(request):
        return HttpResponse("ok")

    assert getattr(my_view, "layout_class", None) is TestLayoutOne

    @async_layout(TestLayoutOne)
    async def my_async_view(request):
        return HttpResponse("ok")

    assert getattr(my_async_view, "layout_class", None) is TestLayoutOne


# ── Decorator Smart Routing Integration Tests (Sync) ──────────────────────────


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
)
def test_sync_decorator_smart_routing_same_layout(locmem_templates, rf):
    """HTMX request + same layout cookie: returns partial with Retarget header, no new cookie."""
    locmem_templates(
        {
            "layouts/one.html": "LAYOUT_ONE|{% load layouts %}{% panel 'content' %}{% endpanel %}",
        }
    )

    @layout(TestLayoutOne)
    def my_view(request):
        return HttpResponse("view-content")

    # Cookie matches TestLayoutOne
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "TestLayoutOne"

    response = my_view(request)

    assert response.content == b"view-content"
    assert response.headers.get("HX-Retarget") == "#panel-content"
    assert "HX-Reswap" not in response.headers
    # No Set-Cookie should be present in header since it's a partial
    assert "set-cookie" not in response.headers.get("Set-Cookie", "").lower()


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
)
def test_sync_decorator_smart_routing_different_layout(locmem_templates, rf):
    """HTMX request + different layout cookie: returns full layout with retarget/reswap headers and sets cookie."""
    locmem_templates(
        {
            "layouts/one.html": "LAYOUT_ONE|{% load layouts %}{% panel 'content' %}{% endpanel %}",
        }
    )

    @layout(TestLayoutOne)
    def my_view(request):
        return HttpResponse("view-content")

    # Cookie is TestLayoutTwo (mismatch)
    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "TestLayoutTwo"

    response = my_view(request)

    assert b"LAYOUT_ONE" in response.content
    assert b"view-content" in response.content
    assert response.headers.get("HX-Retarget") == "body"
    assert response.headers.get("HX-Reswap") == "outerHTML"

    # Cookie should be set to TestLayoutOne
    cookie = response.cookies.get("dj_layout_current")
    assert cookie is not None
    assert cookie.value == "TestLayoutOne"


# ── Decorator Smart Routing Integration Tests (Async) ─────────────────────────


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
)
@pytest.mark.asyncio
async def test_async_decorator_smart_routing_same_layout(locmem_templates, rf):
    """Async request + same layout cookie: returns partial with Retarget header."""
    locmem_templates(
        {
            "layouts/one.html": "LAYOUT_ONE|{% load layouts %}{% panel 'content' %}{% endpanel %}",
        }
    )

    @async_layout(TestLayoutOne)
    async def my_view(request):
        return HttpResponse("async-view-content")

    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "TestLayoutOne"

    response = await my_view(request)

    assert response.content == b"async-view-content"
    assert response.headers.get("HX-Retarget") == "#panel-content"
    assert "HX-Reswap" not in response.headers
    assert "set-cookie" not in response.headers.get("Set-Cookie", "").lower()


@override_settings(
    DJ_LAYOUTS={
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
)
@pytest.mark.asyncio
async def test_async_decorator_smart_routing_different_layout(locmem_templates, rf):
    """Async request + different layout: returns full layout and sets cookie."""
    locmem_templates(
        {
            "layouts/one.html": "LAYOUT_ONE|{% load layouts %}{% panel 'content' %}{% endpanel %}",
        }
    )

    @async_layout(TestLayoutOne)
    async def my_view(request):
        return HttpResponse("async-view-content")

    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "TestLayoutTwo"

    response = await my_view(request)

    assert b"LAYOUT_ONE" in response.content
    assert b"async-view-content" in response.content
    assert response.headers.get("HX-Retarget") == "body"
    assert response.headers.get("HX-Reswap") == "outerHTML"

    cookie = response.cookies.get("dj_layout_current")
    assert cookie is not None
    assert cookie.value == "TestLayoutOne"
