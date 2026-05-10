"""
Tests for Phase 2: async panel rendering via asyncio.gather.

All tests in this file use pytest-asyncio (auto mode). Sync panel views are
auto-wrapped with sync_to_async; async panel views run natively.
"""

from __future__ import annotations

import asyncio

import pytest
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory

from dj_layouts.base import Layout, _registry
from dj_layouts.panels import Panel


@pytest.fixture(autouse=True)
def clear_registry():
    snapshot = dict(_registry)
    yield
    _registry.clear()
    _registry.update(snapshot)


@pytest.fixture()
def rf():
    return RequestFactory()


# ── async_render_with_layout ──────────────────────────────────────────────────


async def test_async_render_with_layout_returns_http_response(rf, locmem_templates):
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "hello",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert isinstance(response, HttpResponse)
    assert b"hello" in response.content


async def test_async_render_with_layout_layout_context_available_in_template(
    rf, locmem_templates
):
    """layout_context is set before the main template renders."""
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "SITE:{{ request.layout_context.site_name }}",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        layout_context_defaults = {"site_name": "AsyncSite"}

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert b"SITE:AsyncSite" in response.content


# ── Sync panel auto-wrapping ──────────────────────────────────────────────────


async def test_sync_callable_panel_runs_correctly(rf, locmem_templates):
    """Sync callable panels are auto-wrapped with sync_to_async."""
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'nav' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    def sync_nav(request, **kwargs):
        return HttpResponse("<nav>sync</nav>")

    class TLayout(Layout):
        template = "layouts/t.html"
        nav = Panel(sync_nav)

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert b"<nav>sync</nav>" in response.content


# ── Native async panels ───────────────────────────────────────────────────────


async def test_async_callable_panel_runs_correctly(rf, locmem_templates):
    """Native async callable panels are awaited directly."""
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'nav' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    async def async_nav(request, **kwargs):
        return HttpResponse("<nav>async</nav>")

    class TLayout(Layout):
        template = "layouts/t.html"
        nav = Panel(async_nav)

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert b"<nav>async</nav>" in response.content


# ── Concurrency ───────────────────────────────────────────────────────────────


async def test_panels_run_concurrently(rf, locmem_templates):
    """Two async panels run concurrently, not sequentially."""
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}"
                "{% panel 'a' %}{% endpanel %}"
                "{% panel 'b' %}{% endpanel %}"
                "{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )

    # Use an asyncio.Event to prove both panels ran concurrently.
    # Each panel sets its own ready event and then waits for the other's.
    # If panels ran sequentially this would deadlock; concurrent → both complete.
    event_a = asyncio.Event()
    event_b = asyncio.Event()

    async def panel_a(request, **kwargs):
        event_a.set()
        await asyncio.wait_for(event_b.wait(), timeout=2.0)
        return HttpResponse("A")

    async def panel_b(request, **kwargs):
        event_b.set()
        await asyncio.wait_for(event_a.wait(), timeout=2.0)
        return HttpResponse("B")

    class TLayout(Layout):
        template = "layouts/t.html"
        a = Panel(panel_a)
        b = Panel(panel_b)

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert b"A" in response.content
    assert b"B" in response.content


async def test_panel_results_in_definition_order(rf, locmem_templates):
    """Results are assembled in panel-definition order regardless of completion order."""
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}"
                "{% panel 'slow' %}{% endpanel %}"
                "{% panel 'fast' %}{% endpanel %}"
                "{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )

    order: list[str] = []

    async def slow_panel(request, **kwargs):
        await asyncio.sleep(0.05)
        order.append("slow")
        return HttpResponse("SLOW")

    async def fast_panel(request, **kwargs):
        order.append("fast")
        return HttpResponse("FAST")

    class TLayout(Layout):
        template = "layouts/t.html"
        slow = Panel(slow_panel)
        fast = Panel(fast_panel)

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    content = response.content.decode()
    # "SLOW" must appear before "FAST" in the rendered output (definition order),
    # even though fast_panel finished first
    assert content.index("SLOW") < content.index("FAST")
    # But fast_panel should have completed first
    assert order == ["fast", "slow"]


# ── Error isolation ───────────────────────────────────────────────────────────


async def test_failing_panel_does_not_block_others(rf, locmem_templates, settings):
    """A failing panel calls on_panel_error; other panels still complete."""
    settings.DEBUG = False
    from dj_layouts.rendering import async_render_with_layout

    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}"
                "{% panel 'bad' %}{% endpanel %}"
                "{% panel 'good' %}{% endpanel %}"
                "{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )

    async def bad_panel(request, **kwargs):
        raise RuntimeError("panel exploded")

    async def good_panel(request, **kwargs):
        return HttpResponse("GOOD")

    error_calls: list[str] = []

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(bad_panel)
        good = Panel(good_panel)

        def on_panel_error(self, request, error):
            error_calls.append(error.panel_name)
            return "<p>fallback</p>"

    request = rf.get("/")
    response = await async_render_with_layout(request, TLayout, "partial.html")
    assert error_calls == ["bad"]
    assert b"GOOD" in response.content
    assert b"fallback" in response.content


async def test_failing_panel_raises_in_debug(rf, locmem_templates, settings):
    """In debug mode, panel errors raise PanelRenderError."""
    from dj_layouts.errors import PanelRenderError
    from dj_layouts.rendering import async_render_with_layout

    settings.DEBUG = True
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'bad' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    async def bad_panel(request, **kwargs):
        raise RuntimeError("debug error")

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(bad_panel)

    request = rf.get("/")
    with pytest.raises(PanelRenderError):
        await async_render_with_layout(request, TLayout, "partial.html")


# ── @async_layout decorator ───────────────────────────────────────────────────


def test_async_layout_raises_for_sync_view():
    """@async_layout applied to a sync function raises TypeError at decoration time."""
    from dj_layouts.decorators import async_layout

    class TLayout(Layout):
        template = "layouts/t.html"

    with pytest.raises(TypeError, match="requires an async view function"):

        @async_layout(TLayout)
        def sync_view(request):  # type: ignore[return]
            ...


def test_async_layout_raises_when_combined_with_panel_only():
    """@async_layout + @panel_only are mutually exclusive."""
    from dj_layouts.decorators import async_layout, panel_only

    class TLayout(Layout):
        template = "layouts/t.html"

    with pytest.raises(TypeError, match="mutually exclusive"):

        @async_layout(TLayout)
        @panel_only
        async def view(request):  # type: ignore[return]
            ...


async def test_async_layout_decorator_wraps_response(rf, locmem_templates):
    from dj_layouts.decorators import async_layout

    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}"
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    @async_layout(TLayout)
    async def my_view(request):
        return HttpResponse("<h1>Hello</h1>")

    request = rf.get("/")
    response = await my_view(request)
    assert b"LAYOUT:" in response.content
    assert b"<h1>Hello</h1>" in response.content


async def test_async_layout_decorator_layout_context_available_in_view(
    rf, locmem_templates
):
    """layout_context is set before the wrapped async view executes."""
    from dj_layouts.decorators import async_layout

    locmem_templates(
        {"layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}"}
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        layout_context_defaults = {"site": "Async"}

    ctx_seen: dict = {}

    @async_layout(TLayout)
    async def my_view(request):
        ctx_seen["ctx"] = getattr(request, "layout_context", None)
        return HttpResponse("")

    request = rf.get("/")
    await my_view(request)
    assert ctx_seen["ctx"] is not None
    assert ctx_seen["ctx"]["site"] == "Async"


async def test_async_layout_noop_when_role_is_panel(rf, locmem_templates):
    from dj_layouts.decorators import async_layout

    locmem_templates(
        {"layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}"}
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    @async_layout(TLayout)
    async def my_view(request):
        return HttpResponse("panel-content")

    request = rf.get("/")
    request.layout_role = "panel"
    response = await my_view(request)
    assert response.content == b"panel-content"


async def test_async_layout_passes_through_redirect(rf, locmem_templates):
    from django.http import HttpResponseRedirect

    from dj_layouts.decorators import async_layout

    locmem_templates(
        {"layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}"}
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    @async_layout(TLayout)
    async def my_view(request):
        return HttpResponseRedirect("/other/")

    request = rf.get("/")
    response = await my_view(request)
    assert response.status_code == 302


async def test_async_layout_passes_through_streaming(rf, locmem_templates):
    from dj_layouts.decorators import async_layout

    locmem_templates(
        {"layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}"}
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    @async_layout(TLayout)
    async def my_view(request):
        return StreamingHttpResponse(iter([b"stream"]))

    request = rf.get("/")
    response = await my_view(request)
    assert isinstance(response, StreamingHttpResponse)


async def test_async_layout_panel_receives_cloned_request(rf, locmem_templates):
    """Async panel sources receive a cloned GET request."""
    from dj_layouts.decorators import async_layout

    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}{% panel 'spy' %}{% endpanel %}{% panel 'content' %}{% endpanel %}"
            )
        }
    )
    seen: dict = {}

    async def spy_panel(request, **kwargs):
        seen["method"] = request.method
        seen["role"] = getattr(request, "layout_role", None)
        return HttpResponse("")

    class TLayout(Layout):
        template = "layouts/t.html"
        spy = Panel(spy_panel)

    @async_layout(TLayout)
    async def my_view(request):
        return HttpResponse("")

    request = rf.post("/", data={"x": "y"})
    await my_view(request)
    assert seen["method"] == "GET"
    assert seen["role"] == "panel"
