"""Tests for render queues (Phase 3)."""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from dj_layouts.base import Layout, _registry
from dj_layouts.queues import (
    BaseQueue,
    RenderQueue,
    ScriptItem,
    ScriptQueue,
    StyleItem,
    StyleQueue,
    add_script,
    add_style,
    add_to_queue,
)
from dj_layouts.rendering import async_render_with_layout, render_with_layout


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


# ── BaseQueue deduplication ───────────────────────────────────────────────────


def test_base_queue_deduplicates():
    q: BaseQueue = ScriptQueue()
    item = ScriptItem(src="/a.js")
    q.add(item)
    q.add(item)
    assert len(q._items) == 1


def test_base_queue_preserves_insertion_order():
    q: BaseQueue = ScriptQueue()
    a = ScriptItem(src="/a.js")
    b = ScriptItem(src="/b.js")
    c = ScriptItem(src="/c.js")
    q.add(a)
    q.add(b)
    q.add(c)
    assert q._items == [a, b, c]


def test_base_queue_merge_from_deduplicates():
    q1: BaseQueue = ScriptQueue()
    q2: BaseQueue = ScriptQueue()
    item = ScriptItem(src="/a.js")
    q1.add(item)
    q2.add(item)
    q1.merge_from(q2)
    assert len(q1._items) == 1


def test_base_queue_merge_from_preserves_order():
    q1: BaseQueue = ScriptQueue()
    q2: BaseQueue = ScriptQueue()
    a = ScriptItem(src="/a.js")
    b = ScriptItem(src="/b.js")
    q1.add(a)
    q2.add(b)
    q1.merge_from(q2)
    assert q1._items == [a, b]


# ── ScriptQueue rendering ─────────────────────────────────────────────────────


def test_script_queue_renders_src():
    q = ScriptQueue()
    q.add(ScriptItem(src="/js/app.js"))
    assert q.render() == '<script src="/js/app.js"></script>'


def test_script_queue_renders_async():
    q = ScriptQueue()
    q.add(ScriptItem(src="/js/app.js", is_async=True))
    assert q.render() == '<script async src="/js/app.js"></script>'


def test_script_queue_renders_defer():
    q = ScriptQueue()
    q.add(ScriptItem(src="/js/app.js", is_deferred=True))
    assert q.render() == '<script defer src="/js/app.js"></script>'


def test_script_queue_renders_type():
    q = ScriptQueue()
    q.add(ScriptItem(src="/js/app.js", type="module"))
    assert q.render() == '<script type="module" src="/js/app.js"></script>'


def test_script_queue_renders_inline():
    q = ScriptQueue()
    q.add(ScriptItem(inline="console.log(1)"))
    assert q.render() == "<script>console.log(1)</script>"


def test_script_queue_renders_multiple_joined_by_newline():
    q = ScriptQueue()
    q.add(ScriptItem(src="/a.js"))
    q.add(ScriptItem(src="/b.js"))
    assert q.render() == '<script src="/a.js"></script>\n<script src="/b.js"></script>'


def test_script_queue_empty_renders_empty_string():
    assert ScriptQueue().render() == ""


# ── StyleQueue rendering ──────────────────────────────────────────────────────


def test_style_queue_renders_href():
    q = StyleQueue()
    q.add(StyleItem(href="/css/app.css"))
    assert q.render() == '<link rel="stylesheet" href="/css/app.css">'


def test_style_queue_renders_media():
    q = StyleQueue()
    q.add(StyleItem(href="/css/print.css", media="print"))
    assert q.render() == '<link rel="stylesheet" href="/css/print.css" media="print">'


def test_style_queue_renders_inline():
    q = StyleQueue()
    q.add(StyleItem(inline=".x { color: red; }"))
    assert q.render() == "<style>.x { color: red; }</style>"


def test_style_queue_empty_renders_empty_string():
    assert StyleQueue().render() == ""


# ── RenderQueue ───────────────────────────────────────────────────────────────


def test_render_queue_passes_items_to_template(locmem_templates):
    locmem_templates({"myapp/q.html": "{% for item in items %}{{ item }}|{% endfor %}"})
    q = RenderQueue(template="myapp/q.html")
    q.add("alpha")
    q.add("beta")
    assert q.render() == "alpha|beta|"


def test_render_queue_deduplicates_strings():
    q = RenderQueue(template="myapp/q.html")
    q.add("x")
    q.add("x")
    assert q._items == ["x"]


def test_render_queue_new_instance_has_same_template():
    q = RenderQueue(template="myapp/q.html")
    fresh = q._new_instance()
    assert fresh.template == "myapp/q.html"
    assert fresh._items == []


# ── View-side API ─────────────────────────────────────────────────────────────


def test_add_script_requires_layout_queues():
    request = RequestFactory().get("/")
    with pytest.raises(AttributeError, match="layout_queues"):
        add_script(request, "/js/app.js")


def test_add_script_adds_to_scripts_queue():
    request = RequestFactory().get("/")
    request.layout_queues = {"scripts": ScriptQueue()}
    add_script(request, "/js/app.js")
    assert request.layout_queues["scripts"]._items == [ScriptItem(src="/js/app.js")]


def test_add_script_inline():
    request = RequestFactory().get("/")
    request.layout_queues = {"scripts": ScriptQueue()}
    add_script(request, inline="alert(1)")
    assert request.layout_queues["scripts"]._items == [ScriptItem(inline="alert(1)")]


def test_add_style_adds_to_styles_queue():
    request = RequestFactory().get("/")
    request.layout_queues = {"styles": StyleQueue()}
    add_style(request, "/css/app.css")
    assert request.layout_queues["styles"]._items == [StyleItem(href="/css/app.css")]


def test_add_to_queue_adds_string():
    request = RequestFactory().get("/")
    request.layout_queues = {"head_extras": RenderQueue(template="t.html")}
    add_to_queue(request, "head_extras", "<meta>")
    assert request.layout_queues["head_extras"]._items == ["<meta>"]


def test_add_to_queue_unknown_name_raises():
    request = RequestFactory().get("/")
    request.layout_queues = {}
    with pytest.raises(KeyError, match="unknown"):
        add_to_queue(request, "unknown", "item")


# ── Layout queue discovery ────────────────────────────────────────────────────


def test_layout_discovers_queue_configs():
    class _DiscoveryLayout(Layout):
        template = "t.html"
        scripts = ScriptQueue()
        styles = StyleQueue()

    assert "scripts" in _DiscoveryLayout._queue_configs
    assert "styles" in _DiscoveryLayout._queue_configs
    assert isinstance(_DiscoveryLayout._queue_configs["scripts"], ScriptQueue)


def test_create_queues_returns_fresh_instances():
    class _FreshLayout(Layout):
        template = "t.html"
        scripts = ScriptQueue()

    q1 = _FreshLayout._create_queues()
    q2 = _FreshLayout._create_queues()
    assert q1["scripts"] is not q2["scripts"]
    assert q1["scripts"] is not _FreshLayout._queue_configs["scripts"]


def test_layout_queue_configs_are_inherited():
    class _ParentLayout(Layout):
        template = "t.html"
        scripts = ScriptQueue()

    class _ChildLayout(_ParentLayout):
        template = "t.html"
        styles = StyleQueue()

    assert "scripts" in _ChildLayout._queue_configs
    assert "styles" in _ChildLayout._queue_configs


# ── Integration: render_with_layout queue flow ────────────────────────────────


@pytest.fixture()
def simple_queue_layout(locmem_templates):
    """Layout with scripts + styles and a renderscripts/renderstyles layout template."""
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


def test_add_script_in_view_appears_in_output(simple_queue_layout, rf, locmem_templates):
    """add_script called before render_with_layout (via decorator) appears in output."""
    from dj_layouts.decorators import layout

    locmem_templates(
        {
            "layouts/sq.html": (
                "{% load layouts %}{% renderscripts %}|{% renderstyles %}"
            ),
            "view_content.html": "",
        }
    )

    @layout(simple_queue_layout)
    def my_view(request):
        add_script(request, "/js/app.js")
        return HttpResponse("")

    request = rf.get("/")
    request.layout_role = None
    response = my_view(request)
    assert '<script src="/js/app.js"></script>' in response.content.decode()


def test_renderscripts_noop_when_empty(simple_queue_layout, rf):
    request = rf.get("/")
    response = render_with_layout(request, simple_queue_layout, "content_empty.html")
    html = response.content.decode()
    assert "<script" not in html


def test_dedup_script_added_by_two_panels(locmem_templates, rf):
    """Duplicate script added by two panels is rendered only once."""
    from dj_layouts.panels import Panel

    locmem_templates(
        {
            "layouts/dedup.html": "{% load layouts %}{% renderscripts %}",
            "content_empty.html": "",
        }
    )

    def panel_fn(request, **kwargs):
        add_script(request, "/js/shared.js")
        return HttpResponse("")

    class DedupLayout(Layout):
        template = "layouts/dedup.html"
        scripts = ScriptQueue()
        panel_a = Panel(panel_fn)
        panel_b = Panel(panel_fn)

    request = rf.get("/")
    response = render_with_layout(request, DedupLayout, "content_empty.html")
    html = response.content.decode()
    assert html.count('<script src="/js/shared.js">') == 1


def test_panel_queue_ordering_follows_definition_order(locmem_templates, rf):
    """Panel A defined before Panel B means A's scripts precede B's."""
    from dj_layouts.panels import Panel

    locmem_templates(
        {
            "layouts/order.html": "{% load layouts %}{% renderscripts %}",
            "content_empty.html": "",
        }
    )

    def panel_a_fn(request, **kwargs):
        add_script(request, "/js/a.js")
        return HttpResponse("")

    def panel_b_fn(request, **kwargs):
        add_script(request, "/js/b.js")
        return HttpResponse("")

    class OrderLayout(Layout):
        template = "layouts/order.html"
        scripts = ScriptQueue()
        panel_a = Panel(panel_a_fn)
        panel_b = Panel(panel_b_fn)

    request = rf.get("/")
    response = render_with_layout(request, OrderLayout, "content_empty.html")
    html = response.content.decode()
    pos_a = html.index("/js/a.js")
    pos_b = html.index("/js/b.js")
    assert pos_a < pos_b


def test_render_queue_with_user_template(locmem_templates, rf):
    """RenderQueue passes items list to its template."""
    from dj_layouts.panels import Panel

    locmem_templates(
        {
            "layouts/rq.html": "{% load layouts %}{% renderqueue 'extras' %}",
            "extras.html": "{% for item in items %}{{ item|safe }}{% endfor %}",
            "content_empty.html": "",
        }
    )

    def panel_fn(request, **kwargs):
        add_to_queue(request, "extras", "<meta>")
        return HttpResponse("")

    class RQLayout(Layout):
        template = "layouts/rq.html"
        extras = RenderQueue(template="extras.html")
        panel_a = Panel(panel_fn)

    request = rf.get("/")
    response = render_with_layout(request, RQLayout, "content_empty.html")
    assert "<meta>" in response.content.decode()


def test_inline_script_block_tag(locmem_templates, rf):
    """Block-form addscript in content template renders content inside <script> tags."""
    locmem_templates(
        {
            "layouts/inline.html": "{% load layouts %}{% renderscripts %}",
            "content_with_script.html": (
                "{% load layouts %}"
                "{% addscript %}console.log(1);{% endaddscript %}"
            ),
        }
    )

    class InlineLayout(Layout):
        template = "layouts/inline.html"
        scripts = ScriptQueue()

    request = rf.get("/")
    response = render_with_layout(request, InlineLayout, "content_with_script.html")
    assert "<script>console.log(1);</script>" in response.content.decode()


# ── Async: ordering follows definition order despite concurrent execution ──────


@pytest.mark.asyncio
async def test_async_panel_queue_ordering_follows_definition_order(locmem_templates, rf):
    """
    Even when panels execute concurrently, queue items from Panel A (defined first)
    precede Panel B's items in the rendered output.
    """
    from dj_layouts.panels import Panel

    locmem_templates(
        {
            "layouts/async_order.html": "{% load layouts %}{% renderscripts %}",
            "content_empty.html": "",
        }
    )

    def panel_slow_fn(request, **kwargs):
        add_script(request, "/js/slow.js")
        return HttpResponse("")

    def panel_fast_fn(request, **kwargs):
        add_script(request, "/js/fast.js")
        return HttpResponse("")

    class AsyncOrderLayout(Layout):
        template = "layouts/async_order.html"
        scripts = ScriptQueue()
        panel_slow = Panel(panel_slow_fn)  # defined first → scripts come first
        panel_fast = Panel(panel_fast_fn)

    request = rf.get("/")
    response = await async_render_with_layout(request, AsyncOrderLayout, "content_empty.html")
    html = response.content.decode()
    pos_slow = html.index("/js/slow.js")
    pos_fast = html.index("/js/fast.js")
    assert pos_slow < pos_fast
