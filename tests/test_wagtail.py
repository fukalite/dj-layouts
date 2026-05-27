import pytest

from dj_layouts.base import Layout


# ── Full layout assembly ───────────────────────────────────────────────────────


def test_wagtail_full_request_assembles_layout(rf, wagtail_mixin, locmem_templates):
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates(
        {
            "layouts/base.html": (
                "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}"
            ),
            "page.html": "PAGE-CONTENT",
        }
    )

    class TestLayout(Layout):
        template = "layouts/base.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        template = "page.html"
        layout_class = TestLayout

    response = BlogPage().serve(rf.get("/"))
    assert b"LAYOUT:" in response.content
    assert b"PAGE-CONTENT" in response.content


# ── Preview mode bypass ───────────────────────────────────────────────────────


def test_wagtail_preview_mode_bypasses_layout(rf, wagtail_mixin, locmem_templates):
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates({"layouts/base.html": "LAYOUT", "page.html": "PAGE"})

    class TestLayout(Layout):
        template = "layouts/base.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        layout_class = TestLayout

    request = rf.get("/")
    request.is_preview = True

    response = BlogPage().serve(request)
    assert response.content == b"FAKE-PAGE"


# ── Partial request bypass ────────────────────────────────────────────────────


def test_wagtail_partial_request_bypasses_layout(
    rf, wagtail_mixin, locmem_templates, settings
):
    settings.DJ_LAYOUTS = {
        "PARTIAL_DETECTORS": ["dj_layouts.detection.query_param_detector"]
    }
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates({"layouts/base.html": "LAYOUT", "page.html": "PAGE"})

    class TestLayout(Layout):
        template = "layouts/base.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        layout_class = TestLayout

    response = BlogPage().serve(rf.get("/", {"_partial": "1"}))
    assert response.content == b"FAKE-PAGE"


# ── String layout_class resolution ───────────────────────────────────────────


def test_wagtail_string_layout_class_resolved(rf, wagtail_mixin, locmem_templates):
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates(
        {
            "layouts/base.html": (
                "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}"
            ),
            "page.html": "PAGE-CONTENT",
        }
    )

    class StringTestLayout(Layout):
        template = "layouts/base.html"

    from dj_layouts.base import _registry

    key = next(k for k, v in _registry.items() if v is StringTestLayout)

    class BlogPage(WagtailLayoutMixin, FakePage):
        template = "page.html"
        layout_class = key

    response = BlogPage().serve(rf.get("/"))
    assert b"LAYOUT:" in response.content
    assert b"PAGE-CONTENT" in response.content


# ── Missing layout_class ──────────────────────────────────────────────────────


def test_wagtail_missing_layout_class_raises(rf, wagtail_mixin, locmem_templates):
    from django.core.exceptions import ImproperlyConfigured

    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates({})

    class BlogPage(WagtailLayoutMixin, FakePage):
        layout_class = None

    with pytest.raises(ImproperlyConfigured, match="layout_class"):
        BlogPage().serve(rf.get("/"))


# ── layout_panels override ────────────────────────────────────────────────────


def test_wagtail_layout_panels_passed_as_override(rf, wagtail_mixin, locmem_templates):
    from dj_layouts.panels import Panel

    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates(
        {
            "layouts/with_nav.html": (
                "{% load layouts %}"
                "{% panel 'nav' %}no-nav{% endpanel %}"
                "|{% panel 'content' %}{% endpanel %}"
            ),
            "page.html": "PAGE",
        }
    )

    class NavLayout(Layout):
        template = "layouts/with_nav.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        template = "page.html"
        layout_class = NavLayout
        layout_panels = {"nav": Panel(lambda request, **kw: "NAV-HTML")}

    response = BlogPage().serve(rf.get("/"))
    assert b"NAV-HTML" in response.content
    assert b"PAGE" in response.content


# ── Importing without Wagtail raises ImportError ──────────────────────────────


def test_wagtail_module_requires_wagtail_installed():
    import importlib
    import sys
    from unittest.mock import patch

    sys.modules.pop("dj_layouts.wagtail", None)
    with patch.dict(sys.modules, {"wagtail": None, "wagtail.models": None}):
        with pytest.raises(ImportError, match="wagtail"):
            importlib.import_module("dj_layouts.wagtail")
    sys.modules.pop("dj_layouts.wagtail", None)


# ── HTMX Smart Routing ────────────────────────────────────────────────────────


def test_wagtail_smart_routing_same_layout(
    rf, wagtail_mixin, locmem_templates, settings
):
    settings.DJ_LAYOUTS = {
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates(
        {
            "layouts/base.html": "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}",
            "page.html": "PAGE-CONTENT",
        }
    )

    class TestLayout(Layout):
        template = "layouts/base.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        template = "page.html"
        layout_class = TestLayout

    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "TestLayout"

    response = BlogPage().serve(request)
    assert response.content == b"FAKE-PAGE"
    assert response.headers.get("HX-Retarget") == "#panel-content"
    assert "HX-Reswap" not in response.headers
    assert "set-cookie" not in response.headers.get("Set-Cookie", "").lower()


def test_wagtail_smart_routing_different_layout(
    rf, wagtail_mixin, locmem_templates, settings
):
    settings.DJ_LAYOUTS = {
        "HTMX_SMART_ROUTING": True,
        "HTMX_CONTENT_TARGET": "#panel-content",
        "HTMX_COOKIE_NAME": "dj_layout_current",
        "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    }
    WagtailLayoutMixin, FakePage = wagtail_mixin
    locmem_templates(
        {
            "layouts/base.html": "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}",
            "page.html": "PAGE-CONTENT",
        }
    )

    class TestLayout(Layout):
        template = "layouts/base.html"

    class BlogPage(WagtailLayoutMixin, FakePage):
        template = "page.html"
        layout_class = TestLayout

    request = rf.get("/", HTTP_HX_REQUEST="true")
    request.COOKIES["dj_layout_current"] = "OtherLayout"

    response = BlogPage().serve(request)
    assert b"LAYOUT:" in response.content
    assert b"PAGE-CONTENT" in response.content
    assert response.headers.get("HX-Retarget") == "body"
    assert response.headers.get("HX-Reswap") == "outerHTML"

    cookie = response.cookies.get("dj_layout_current")
    assert cookie is not None
    assert cookie.value == "TestLayout"
