import pytest
from django.template import Context, RequestContext, Template
from django.test import RequestFactory


rf = RequestFactory()


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
        request = rf.get("/")
        queues = {"scripts": ScriptQueue(), "styles": StyleQueue()}
        if extra_queues:
            queues.update(extra_queues)
        request.layout_queues = queues
        t = Template(template_str)
        html = t.render(RequestContext(request, {}))
        return html, request

    return _render


def test_panel_tag_renders_content_when_present(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'nav' %}fallback{% endpanel %}",
        {"nav": "<nav>Real Nav</nav>"},
    )
    assert html == "<nav>Real Nav</nav>"


def test_panel_tag_renders_fallback_when_empty_string(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'nav' %}fallback{% endpanel %}",
        {"nav": ""},
    )
    assert html == "fallback"


def test_panel_tag_renders_fallback_when_absent(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'nav' %}fallback{% endpanel %}",
        {},
    )
    assert html == "fallback"


def test_panel_tag_empty_fallback(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'nav' %}{% endpanel %}",
        {},
    )
    assert html == ""


def test_panel_tag_multiple_panels(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'a' %}A-fallback{% endpanel %}{% panel 'b' %}B-fallback{% endpanel %}",
        {"a": "<p>A</p>", "b": ""},
    )
    assert "<p>A</p>" in html
    assert "B-fallback" in html


def test_panel_tag_fallback_can_contain_html(render_panel):
    html = render_panel(
        "{% load layouts %}{% panel 'nav' %}<p>default nav</p>{% endpanel %}",
        {},
    )
    assert html == "<p>default nav</p>"


# ── addscript tag ─────────────────────────────────────────────────────────────


def test_addscript_url_enqueues_script(render_with_queues):
    html, request = render_with_queues("{% load layouts %}{% addscript '/js/app.js' %}")
    from dj_layouts.queues import ScriptItem

    assert ScriptItem(src="/js/app.js") in request.layout_queues["scripts"]._items


def test_addscript_async_flag(render_with_queues):
    _, request = render_with_queues(
        "{% load layouts %}{% addscript '/js/app.js' async %}"
    )

    assert request.layout_queues["scripts"]._items[0].is_async is True


def test_addscript_defer_flag(render_with_queues):
    _, request = render_with_queues(
        "{% load layouts %}{% addscript '/js/app.js' defer %}"
    )

    assert request.layout_queues["scripts"]._items[0].is_deferred is True


def test_addscript_block_form_strips_whitespace(render_with_queues):
    _, request = render_with_queues(
        "{% load layouts %}{% addscript %}\n  console.log(1);\n{% endaddscript %}"
    )
    from dj_layouts.queues import ScriptItem

    assert request.layout_queues["scripts"]._items == [
        ScriptItem(inline="console.log(1);")
    ]


def test_addscript_produces_no_output(render_with_queues):
    html, _ = render_with_queues("{% load layouts %}{% addscript '/js/app.js' %}")
    assert html == ""


# ── addstyle tag ──────────────────────────────────────────────────────────────


def test_addstyle_url_enqueues_style(render_with_queues):
    _, request = render_with_queues("{% load layouts %}{% addstyle '/css/app.css' %}")
    from dj_layouts.queues import StyleItem

    assert StyleItem(href="/css/app.css") in request.layout_queues["styles"]._items


def test_addstyle_media_attribute(render_with_queues):
    _, request = render_with_queues(
        "{% load layouts %}{% addstyle '/css/print.css' media=\"print\" %}"
    )
    assert request.layout_queues["styles"]._items[0].media == "print"


def test_addstyle_block_form_strips_whitespace(render_with_queues):
    _, request = render_with_queues(
        "{% load layouts %}{% addstyle %}\n  .x { color: red; }\n{% endaddstyle %}"
    )
    from dj_layouts.queues import StyleItem

    assert request.layout_queues["styles"]._items == [
        StyleItem(inline=".x { color: red; }")
    ]


# ── enqueue tag ───────────────────────────────────────────────────────────────


def test_enqueue_adds_to_named_queue(render_with_queues, locmem_templates):
    from dj_layouts.queues import RenderQueue

    locmem_templates(
        {"t.html": "{% load layouts %}{% enqueue 'extras' %}<meta>{% endenqueue %}"}
    )
    extra = {"extras": RenderQueue(template="e.html")}
    _, request = render_with_queues(
        "{% load layouts %}{% enqueue 'extras' %}<meta>{% endenqueue %}", extra
    )
    assert "<meta>" in request.layout_queues["extras"]._items


# ── renderscripts tag ─────────────────────────────────────────────────────────


def test_renderscripts_outputs_script_tags(render_with_queues):

    _, request = render_with_queues("{% load layouts %}{% addscript '/js/a.js' %}")
    # Now render the output tag
    from django.template import RequestContext, Template

    t = Template("{% load layouts %}{% renderscripts %}")
    html = t.render(RequestContext(request, {}))
    assert '<script src="/js/a.js"></script>' in html


def test_renderscripts_noop_when_empty(render_with_queues):
    html, _ = render_with_queues("{% load layouts %}{% renderscripts %}")
    assert html == ""


# ── renderstyles tag ──────────────────────────────────────────────────────────


def test_renderstyles_outputs_link_tags(render_with_queues):
    _, request = render_with_queues("{% load layouts %}{% addstyle '/css/a.css' %}")
    from django.template import RequestContext, Template

    t = Template("{% load layouts %}{% renderstyles %}")
    html = t.render(RequestContext(request, {}))
    assert '<link rel="stylesheet" href="/css/a.css">' in html


def test_renderstyles_noop_when_empty(render_with_queues):
    html, _ = render_with_queues("{% load layouts %}{% renderstyles %}")
    assert html == ""


# ── renderqueue tag ───────────────────────────────────────────────────────────


def test_renderqueue_calls_queue_render(locmem_templates, rf):
    from dj_layouts.queues import RenderQueue

    locmem_templates(
        {
            "t.html": "{% load layouts %}{% renderqueue 'extras' %}",
            "e.html": "{% for item in items %}{{ item|safe }}{% endfor %}",
        }
    )

    request = rf.get("/")
    request.layout_queues = {"extras": RenderQueue(template="e.html")}
    request.layout_queues["extras"].add("<meta>")

    from django.template import RequestContext, Template

    t = Template("{% load layouts %}{% renderqueue 'extras' %}")
    html = t.render(RequestContext(request, {}))
    assert "<meta>" in html


def test_renderqueue_noop_when_empty(locmem_templates, render_with_queues):
    from dj_layouts.queues import RenderQueue

    locmem_templates({"e.html": "items"})
    extra = {"extras": RenderQueue(template="e.html")}
    html, _ = render_with_queues("{% load layouts %}{% renderqueue 'extras' %}", extra)
    assert html == ""
