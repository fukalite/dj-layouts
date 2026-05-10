from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.template import Context, RequestContext, Template
from django.test import RequestFactory

from dj_layouts.base import Layout, _registry
from dj_layouts.detection import _reset_detector_cache
from dj_layouts.panels import Panel


# ── Infrastructure ─────────────────────────────────────────────────────────────


@pytest.fixture()
def rf():
    return RequestFactory()


@pytest.fixture(autouse=True)
def clear_registry():
    """Isolate each test from leftover Layout registrations."""
    snapshot = dict(_registry)
    yield
    _registry.clear()
    _registry.update(snapshot)


@pytest.fixture(autouse=True)
def reset_detectors():
    """Ensure the detector cache is clean before and after each test."""
    _reset_detector_cache()
    yield
    _reset_detector_cache()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the default cache after each test."""
    from django.core.cache import caches

    yield
    caches["default"].clear()


@pytest.fixture(autouse=True)
def clear_deferred_layout_refs():
    """Isolate each test from leftover string refs tracked by @layout/@async_layout."""
    from dj_layouts.decorators import _deferred_layout_refs

    snapshot = list(_deferred_layout_refs)
    yield
    _deferred_layout_refs.clear()
    _deferred_layout_refs.extend(snapshot)


@pytest.fixture()
def locmem_templates(settings):
    """
    Configure in-memory templates for isolation, with the layouts tag library
    available (no need for dj_layouts to be in INSTALLED_APPS for tag discovery).
    """

    def configure(templates_dict: dict) -> None:
        settings.TEMPLATES = [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": False,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                    ],
                    "libraries": {
                        "layouts": "dj_layouts.templatetags.layouts",
                    },
                    "loaders": [
                        ("django.template.loaders.locmem.Loader", templates_dict),
                    ],
                },
            }
        ]

    return configure


# ── test_panels fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def request_with_context(rf):
    from dj_layouts.context import LayoutContext

    req = rf.get("/")
    req.layout_context = LayoutContext({"site": "Test"})
    return req


@pytest.fixture()
def url_conf(settings):
    """URL patterns for panel URL-name resolution tests (ROOT_URLCONF=tests.test_panels)."""
    from django.urls import path

    import tests.test_panels as mod

    patterns = [
        path("nav/", mod._nav_view, name="test_nav"),
        path("ctx/", mod._ctx_view, name="test_ctx"),
    ]
    settings.ROOT_URLCONF = "tests.test_panels"
    return patterns


# ── test_decorators fixtures ───────────────────────────────────────────────────


@pytest.fixture()
def decorator_layout(locmem_templates):
    """Simple layout for decorator tests."""
    locmem_templates(
        {
            "layouts/simple.html": (
                "{% load layouts %}LAYOUT:{% panel 'content' %}no content{% endpanel %}"
            ),
        }
    )

    class SimpleLayout(Layout):
        template = "layouts/simple.html"

    return SimpleLayout


# ── test_cache fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def cache_test_layout(locmem_templates):
    """Layout with a cached nav panel for cache integration tests."""
    from dj_layouts.cache import sitewide

    locmem_templates(
        {
            "layouts/cache_test.html": (
                "{% load layouts %}{% panel 'nav' %}{% endpanel %}"
                "|{% panel 'content' %}{% endpanel %}"
            ),
            "content.html": "",
        }
    )

    call_count = {"nav": 0}

    def nav_fn(request, **kwargs):
        call_count["nav"] += 1
        return HttpResponse(f"nav-{call_count['nav']}")

    class CacheTestLayout(Layout):
        template = "layouts/cache_test.html"
        nav = Panel(nav_fn, cache=sitewide(timeout=60))

    return CacheTestLayout, call_count


# ── test_queues fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def simple_queue_layout(locmem_templates):
    """Layout with scripts + styles queues and a renderscripts/renderstyles template."""
    from dj_layouts.queues import ScriptQueue, StyleQueue

    locmem_templates(
        {
            "layouts/sq.html": (
                "{% load layouts %}"
                "{% renderscripts %}"
                "|"
                "{% renderstyles %}"
            ),
            "content_empty.html": "",
        }
    )

    class SimpleQueueLayout(Layout):
        template = "layouts/sq.html"
        scripts = ScriptQueue()
        styles = StyleQueue()

    return SimpleQueueLayout


# ── test_templatetags fixtures ─────────────────────────────────────────────────


@pytest.fixture()
def render_panel(locmem_templates):
    """Helper: configure a layout template and render it with given panel context."""

    def _render(template_str: str, panels: dict) -> str:
        locmem_templates({"layouts/t.html": template_str})
        t = Template(template_str)
        return t.render(Context({"_panels": panels}))

    return _render


@pytest.fixture()
def render_with_queues(locmem_templates):
    """Helper: render a template string with a request that has layout queues."""
    from dj_layouts.queues import ScriptQueue, StyleQueue

    def _render(template_str: str, extra_queues: dict | None = None) -> tuple:
        locmem_templates({"t.html": template_str})
        request = RequestFactory().get("/")
        queues = {"scripts": ScriptQueue(), "styles": StyleQueue()}
        if extra_queues:
            queues.update(extra_queues)
        request.layout_queues = queues
        t = Template(template_str)
        html = t.render(RequestContext(request, {}))
        return html, request

    return _render


# ── test_wagtail fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def wagtail_mixin():
    """
    Provide WagtailLayoutMixin with a minimal fake Wagtail Page.

    Patches sys.modules with stub wagtail/wagtail.models modules so that
    dj_layouts.wagtail can be imported without Wagtail installed.
    Yields (WagtailLayoutMixin, FakePage).
    """
    import importlib
    import sys
    import types
    from unittest.mock import patch

    from django.http import HttpResponse

    class FakePage:
        template = "page.html"

        def get_template(self, request, *args, **kwargs):
            return self.template

        def get_context(self, request, *args, **kwargs):
            return {"page": self}

        def serve(self, request, *args, **kwargs):
            return HttpResponse("FAKE-PAGE")

    fake_wagtail = types.ModuleType("wagtail")
    fake_models = types.ModuleType("wagtail.models")
    fake_models.Page = FakePage

    sys.modules.pop("dj_layouts.wagtail", None)

    with patch.dict(sys.modules, {"wagtail": fake_wagtail, "wagtail.models": fake_models}):
        mod = importlib.import_module("dj_layouts.wagtail")
        yield mod.WagtailLayoutMixin, FakePage

    sys.modules.pop("dj_layouts.wagtail", None)
