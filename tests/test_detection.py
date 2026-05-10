"""Tests for partial detection (Phase 5)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import override_settings

from dj_layouts.base import Layout
from dj_layouts.decorators import async_layout, layout
from dj_layouts.detection import (
    htmx_detector,
    is_partial_request,
    never_detector,
    query_param_detector,
)
from dj_layouts.rendering import render_with_layout


# ── Built-in detectors ────────────────────────────────────────────────────────


def test_never_detector_always_false(rf):
    assert never_detector(rf.get("/")) is False
    assert never_detector(rf.get("/", HTTP_HX_REQUEST="true")) is False


def test_htmx_detector_true_on_hx_request_header(rf):
    request = rf.get("/", HTTP_HX_REQUEST="true")
    assert htmx_detector(request) is True


def test_htmx_detector_false_without_header(rf):
    assert htmx_detector(rf.get("/")) is False


def test_htmx_detector_false_on_wrong_value(rf):
    request = rf.get("/", HTTP_HX_REQUEST="1")
    assert htmx_detector(request) is False


def test_query_param_detector_true_on_partial_param(rf):
    assert query_param_detector(rf.get("/?_partial=1")) is True


def test_query_param_detector_false_without_param(rf):
    assert query_param_detector(rf.get("/")) is False


def test_query_param_detector_false_on_wrong_value(rf):
    assert query_param_detector(rf.get("/?_partial=true")) is False


# ── is_partial_request ────────────────────────────────────────────────────────


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.never_detector"]})
def test_is_partial_request_false_with_never_detector(rf):
    assert is_partial_request(rf.get("/")) is False


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
def test_is_partial_request_true_with_htmx_detector(rf):
    assert is_partial_request(rf.get("/", HTTP_HX_REQUEST="true")) is True


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
def test_is_partial_request_false_with_htmx_detector_and_no_header(rf):
    assert is_partial_request(rf.get("/")) is False


@override_settings(
    DJ_LAYOUTS={
        "PARTIAL_DETECTORS": [
            "dj_layouts.detection.never_detector",
            "dj_layouts.detection.htmx_detector",
        ]
    }
)
def test_multiple_detectors_any_one_fires(rf):
    """Any detector returning True is sufficient."""
    assert is_partial_request(rf.get("/", HTTP_HX_REQUEST="true")) is True


@override_settings(
    DJ_LAYOUTS={
        "PARTIAL_DETECTORS": [
            "dj_layouts.detection.never_detector",
            "dj_layouts.detection.query_param_detector",
        ]
    }
)
def test_multiple_detectors_none_fire(rf):
    assert is_partial_request(rf.get("/")) is False


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["not.a.real.module.detector"]})
def test_invalid_detector_path_raises_improperly_configured():
    with pytest.raises(ImproperlyConfigured, match="DJ_LAYOUTS"):
        is_partial_request(None)


# ── Detector exception handling ───────────────────────────────────────────────


def _raising_detector(request):
    raise ValueError("boom")


@override_settings(
    DJ_LAYOUTS={
        "PARTIAL_DETECTORS": ["tests.test_detection._raising_detector"],
        "DETECTOR_RAISE_EXCEPTIONS": False,
    }
)
def test_detector_exception_treated_as_false_by_default(rf):
    """Exception in detector → log at WARNING, treat as False."""
    result = is_partial_request(rf.get("/"))
    assert result is False


@override_settings(
    DJ_LAYOUTS={
        "PARTIAL_DETECTORS": ["tests.test_detection._raising_detector"],
        "DETECTOR_RAISE_EXCEPTIONS": True,
    }
)
def test_detector_exception_reraises_when_setting_true(rf):
    """DETECTOR_RAISE_EXCEPTIONS = True → re-raise detector exceptions."""
    with pytest.raises(ValueError, match="boom"):
        is_partial_request(rf.get("/"))


# ── Integration with @layout ──────────────────────────────────────────────────


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
def test_layout_decorator_partial_returns_view_response_directly(locmem_templates, rf):
    """HTMX request: view runs, response returned, no layout assembly."""
    locmem_templates(
        {
            "layouts/base.html": "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "partial-content",
        }
    )

    class SimpleLayout(Layout):
        template = "layouts/base.html"

    @layout(SimpleLayout)
    def my_view(request):
        return HttpResponse("partial-content")

    request = rf.get("/", HTTP_HX_REQUEST="true")
    response = my_view(request)

    assert response.content == b"partial-content"
    assert b"LAYOUT" not in response.content
    assert request.is_layout_partial is True


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
def test_layout_decorator_non_partial_assembles_layout(locmem_templates, rf):
    """Non-HTMX request: layout assembled normally."""
    locmem_templates(
        {
            "layouts/base.html": "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "",
        }
    )

    class FullLayout(Layout):
        template = "layouts/base.html"

    @layout(FullLayout)
    def my_view(request):
        return HttpResponse("content-here")

    request = rf.get("/")
    response = my_view(request)

    assert b"LAYOUT" in response.content
    assert b"content-here" in response.content
    assert request.is_layout_partial is False


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
@pytest.mark.asyncio
async def test_async_layout_decorator_partial_skips_layout(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/base.html": "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}",
        }
    )

    class AsyncLayout(Layout):
        template = "layouts/base.html"

    @async_layout(AsyncLayout)
    async def my_async_view(request):
        return HttpResponse("async-partial")

    request = rf.get("/", HTTP_HX_REQUEST="true")
    response = await my_async_view(request)

    assert response.content == b"async-partial"
    assert b"LAYOUT" not in response.content
    assert request.is_layout_partial is True


# ── render_with_layout bypasses detection ─────────────────────────────────────


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
def test_render_with_layout_ignores_detection(locmem_templates, rf):
    """render_with_layout always assembles the full layout, regardless of detectors."""
    locmem_templates(
        {
            "layouts/base.html": "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "content.html": "full-content",
        }
    )

    class DirectLayout(Layout):
        template = "layouts/base.html"

    request = rf.get("/", HTTP_HX_REQUEST="true")
    response = render_with_layout(request, DirectLayout, "content.html")

    assert b"LAYOUT" in response.content
    assert b"full-content" in response.content
