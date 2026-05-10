"""Tests for LayoutMixin (Phase 5)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.views.generic import TemplateView, View

from dj_layouts.base import Layout, _registry
from dj_layouts.detection import _reset_detector_cache
from dj_layouts.mixins import LayoutMixin
from dj_layouts.panels import Panel


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def rf():
    return RequestFactory()


@pytest.fixture(autouse=True)
def clear_registry():
    snapshot = dict(_registry)
    yield
    _registry.clear()
    _registry.update(snapshot)


@pytest.fixture(autouse=True)
def reset_detectors():
    _reset_detector_cache()
    yield
    _reset_detector_cache()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _call_view(view_class, request, *args, **kwargs):
    """Call a LayoutMixin CBV and return the response, awaiting if needed."""
    import asyncio

    view = view_class.as_view()
    response = view(request, *args, **kwargs)
    if asyncio.iscoroutine(response):
        response = await response
    return response


# ── Basic assembly ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_layout_mixin_assembles_full_page(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/mixin.html": (
                "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}"
            ),
            "mixin/partial.html": "mixin-content",
        }
    )

    class SimpleLayout(Layout):
        template = "layouts/mixin.html"

    class MyView(LayoutMixin, TemplateView):
        layout_class = SimpleLayout
        template_name = "mixin/partial.html"

    request = rf.get("/")
    response = await _call_view(MyView, request)

    assert b"LAYOUT" in response.content
    assert b"mixin-content" in response.content


@pytest.mark.asyncio
async def test_layout_mixin_with_dotted_string_layout_class(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/mixin_str.html": (
                "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}"
            ),
            "mixin/str_partial.html": "str-content",
        }
    )

    class StringRefLayout(Layout):
        template = "layouts/mixin_str.html"

    class MyView(LayoutMixin, TemplateView):
        layout_class = "tests.StringRefLayout"  # registry key: <app_label>.<ClassName>
        template_name = "mixin/str_partial.html"

    request = rf.get("/")
    response = await _call_view(MyView, request)

    assert b"LAYOUT" in response.content
    assert b"str-content" in response.content


@pytest.mark.asyncio
async def test_layout_mixin_with_panel_override(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/mixin_panel.html": (
                "{% load layouts %}{% panel 'nav' %}default-nav{% endpanel %}"
                "|{% panel 'content' %}{% endpanel %}"
            ),
            "mixin/panel_partial.html": "main-content",
        }
    )

    def custom_nav(request, **kwargs):
        return HttpResponse("custom-nav")

    class PanelLayout(Layout):
        template = "layouts/mixin_panel.html"
        nav = Panel(lambda r, **kw: HttpResponse("default-nav"))

    class MyView(LayoutMixin, TemplateView):
        layout_class = PanelLayout
        layout_panels = {"nav": Panel(custom_nav)}
        template_name = "mixin/panel_partial.html"

    request = rf.get("/")
    response = await _call_view(MyView, request)

    assert b"custom-nav" in response.content
    assert b"default-nav" not in response.content


@pytest.mark.asyncio
async def test_layout_mixin_missing_layout_class_raises(rf):
    class NoClassView(LayoutMixin, View):
        async def get(self, request):
            return HttpResponse("hi")

    request = rf.get("/")
    with pytest.raises(ImproperlyConfigured, match="layout_class"):
        await _call_view(NoClassView, request)


# ── Async handler methods ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_layout_mixin_with_async_get_handler(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/async_mixin.html": (
                "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}"
            ),
        }
    )

    class AsyncLayout(Layout):
        template = "layouts/async_mixin.html"

    class MyAsyncView(LayoutMixin, View):
        layout_class = AsyncLayout

        async def get(self, request):
            return HttpResponse("async-content")

    request = rf.get("/")
    response = await _call_view(MyAsyncView, request)

    assert b"LAYOUT" in response.content
    assert b"async-content" in response.content


# ── Panel role pass-through ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_layout_mixin_noop_when_role_is_panel(locmem_templates, rf):
    locmem_templates({})

    class SomeLayout(Layout):
        template = "layouts/mixin.html"

    class PanelRoleView(LayoutMixin, View):
        layout_class = SomeLayout

        def get(self, request):
            return HttpResponse("panel-output")

    request = rf.get("/")
    request.layout_role = "panel"
    response = await _call_view(PanelRoleView, request)

    assert response.content == b"panel-output"


# ── TemplateResponse force-rendering ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_layout_mixin_force_renders_template_response(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/mixin_tr.html": (
                "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}"
            ),
            "mixin/template_response.html": "template-response-content",
        }
    )

    class TRLayout(Layout):
        template = "layouts/mixin_tr.html"

    # TemplateView returns a TemplateResponse (unrendered until force-rendered)
    class MyView(LayoutMixin, TemplateView):
        layout_class = TRLayout
        template_name = "mixin/template_response.html"

    request = rf.get("/")
    response = await _call_view(MyView, request)

    assert b"LAYOUT" in response.content
    assert b"template-response-content" in response.content


# ── Non-200 pass-through ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_layout_mixin_passes_through_non_200(locmem_templates, rf):
    locmem_templates({"layouts/mixin_404.html": "LAYOUT"})

    class Simple404Layout(Layout):
        template = "layouts/mixin_404.html"

    class RedirectView(LayoutMixin, View):
        layout_class = Simple404Layout

        def get(self, request):
            from django.http import HttpResponseRedirect

            return HttpResponseRedirect("/somewhere/")

    request = rf.get("/")
    response = await _call_view(RedirectView, request)

    assert response.status_code == 302
    assert response["Location"] == "/somewhere/"


# ── Partial detection ─────────────────────────────────────────────────────────


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
@pytest.mark.asyncio
async def test_layout_mixin_partial_skips_layout(locmem_templates, rf):
    """HTMX request: view runs, partial response returned, no layout wrapping."""
    locmem_templates(
        {
            "layouts/mixin_partial.html": "LAYOUT",
            "mixin/htmx_partial.html": "htmx-content",
        }
    )

    class PartialLayout(Layout):
        template = "layouts/mixin_partial.html"

    class MyView(LayoutMixin, TemplateView):
        layout_class = PartialLayout
        template_name = "mixin/htmx_partial.html"

    request = rf.get("/", HTTP_HX_REQUEST="true")
    response = await _call_view(MyView, request)

    assert b"htmx-content" in response.content
    assert b"LAYOUT" not in response.content
    assert request.is_layout_partial is True


@override_settings(DJ_LAYOUTS={"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]})
@pytest.mark.asyncio
async def test_layout_mixin_non_partial_assembles_layout(locmem_templates, rf):
    locmem_templates(
        {
            "layouts/mixin_full.html": (
                "LAYOUT|{% load layouts %}{% panel 'content' %}{% endpanel %}"
            ),
            "mixin/full_partial.html": "full-content",
        }
    )

    class FullLayout(Layout):
        template = "layouts/mixin_full.html"

    class MyView(LayoutMixin, TemplateView):
        layout_class = FullLayout
        template_name = "mixin/full_partial.html"

    request = rf.get("/")
    response = await _call_view(MyView, request)

    assert b"LAYOUT" in response.content
    assert b"full-content" in response.content
    assert request.is_layout_partial is False


# ── view_is_async ─────────────────────────────────────────────────────────────


def test_layout_mixin_view_is_async():
    """LayoutMixin always produces async views."""
    import asyncio

    class SomeLayout(Layout):
        template = "t.html"

    class MyView(LayoutMixin, View):
        layout_class = SomeLayout

        def get(self, request):
            return HttpResponse("hi")

    view = MyView.as_view()
    assert asyncio.iscoroutinefunction(view)
