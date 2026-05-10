import pytest
from django.http import HttpResponse

from dj_layouts.base import Layout
from dj_layouts.panels import Panel
from dj_layouts.rendering import render_with_layout


# ── render_with_layout ────────────────────────────────────────────────────────


def test_render_with_layout_returns_http_response(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "hello",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert isinstance(response, HttpResponse)


def test_render_with_layout_content_panel_contains_view_output(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}LAYOUT:{% panel 'content' %}{% endpanel %}",
            "partial.html": "<h1>My Page</h1>",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html", context={})
    assert b"<h1>My Page</h1>" in response.content
    assert b"LAYOUT:" in response.content


def test_render_with_layout_callable_panel(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'nav' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    def nav_fn(request, **kwargs):
        return HttpResponse("<nav>Nav</nav>")

    class TLayout(Layout):
        template = "layouts/t.html"
        nav = Panel(nav_fn)

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"<nav>Nav</nav>" in response.content


def test_callable_panel_receives_cloned_request(rf, locmem_templates):
    """Callable panel sources receive a cloned request: GET, layout_role='panel', frozen context."""
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'spy' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )
    seen = {}

    def spy_fn(request, **kwargs):
        seen["method"] = request.method
        seen["role"] = getattr(request, "layout_role", None)
        seen["is_partial"] = getattr(request, "is_layout_partial", None)
        return HttpResponse("")

    class TLayout(Layout):
        template = "layouts/t.html"
        spy = Panel(spy_fn)

    request = rf.post("/", data={"x": "y"})
    request.layout_role = "main"
    render_with_layout(request, TLayout, "partial.html")

    assert seen["method"] == "GET"
    assert seen["role"] == "panel"
    assert seen["is_partial"] is False


def test_render_with_layout_string_panel(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'footer' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        footer = Panel("<footer>Footer</footer>")

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"<footer>Footer</footer>" in response.content


def test_render_with_layout_none_panel_shows_fallback(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}{% panel 'sidebar' %}default-sidebar{% endpanel %}"
                "{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        sidebar = Panel(None)

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"default-sidebar" in response.content


def test_render_with_layout_list_panel(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'banner' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    def part1(request, **kwargs):
        return HttpResponse("<p>A</p>")

    class TLayout(Layout):
        template = "layouts/t.html"
        banner = Panel([part1, "<p>B</p>"])

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"<p>A</p>" in response.content
    assert b"<p>B</p>" in response.content


def test_render_with_layout_panel_override(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}{% panel 'sidebar' %}{% endpanel %}{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        sidebar = Panel("<p>class-sidebar</p>")

    request = rf.get("/")
    response = render_with_layout(
        request,
        TLayout,
        "partial.html",
        panels={"sidebar": Panel("<p>override-sidebar</p>")},
    )
    assert b"override-sidebar" in response.content
    assert b"class-sidebar" not in response.content


def test_render_with_layout_context_available_in_layout_template(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}SITE:{{ site_name }}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        layout_context_defaults = {"site_name": "TestSite"}

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"SITE:TestSite" in response.content


def test_layout_context_available_in_main_template(rf, locmem_templates):
    """render_with_layout sets layout_context on request before rendering the main template."""
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "SITE:{{ request.layout_context.site_name }}",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"
        layout_context_defaults = {"site_name": "FromContext"}

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"SITE:FromContext" in response.content


def test_render_with_layout_get_layout_context_merged(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}USER:{{ current_user }}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    class TLayout(Layout):
        template = "layouts/t.html"

        def get_layout_context(self, request):
            return {"current_user": "alice"}

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert b"USER:alice" in response.content


# ── Error handling ────────────────────────────────────────────────────────────


def test_layout_decorated_view_as_callable_panel_noop(rf, locmem_templates):
    """
    A @layout-decorated view used as a callable panel source must not re-wrap itself.
    The cloned panel request has layout_role='panel', so @layout becomes a no-op.
    """
    from dj_layouts.decorators import layout as layout_decorator

    locmem_templates(
        {
            "layouts/outer.html": (
                "{% load layouts %}OUTER:{% panel 'inner' %}{% endpanel %}{% panel 'content' %}{% endpanel %}"
            ),
            "layouts/inner.html": (
                "{% load layouts %}INNER:{% panel 'content' %}{% endpanel %}"
            ),
            "main.html": "main-content",
            "inner.html": "inner-content",
        }
    )

    class InnerLayout(Layout):
        template = "layouts/inner.html"

    @layout_decorator(InnerLayout)
    def inner_view(request):
        return HttpResponse("inner-content")

    class OuterLayout(Layout):
        template = "layouts/outer.html"
        inner = Panel(inner_view)

    request = rf.get("/")
    response = render_with_layout(request, OuterLayout, "main.html")
    # Should contain "inner-content" without double-wrapping
    assert b"inner-content" in response.content
    assert b"OUTER:" in response.content
    # Must NOT contain "INNER:" because the @layout no-op fired
    assert b"INNER:" not in response.content


def test_panel_error_calls_on_panel_error_in_production(rf, locmem_templates, settings):
    settings.DEBUG = False
    locmem_templates(
        {
            "layouts/t.html": (
                "{% load layouts %}ERR:{% panel 'bad' %}{% endpanel %}{% panel 'content' %}{% endpanel %}"
            ),
            "partial.html": "body",
        }
    )
    error_calls = []

    def broken_panel(request, **kwargs):
        raise RuntimeError("panel broke")

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(broken_panel)

        def on_panel_error(self, request, error):
            error_calls.append(error.panel_name)
            return "<p>fallback</p>"

    request = rf.get("/")
    response = render_with_layout(request, TLayout, "partial.html")
    assert error_calls == ["bad"]
    assert b"<p>fallback</p>" in response.content


def test_panel_error_raises_panel_render_error_in_debug(rf, locmem_templates, settings):
    from dj_layouts.errors import PanelRenderError

    settings.DEBUG = True
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'bad' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    def broken_panel(request, **kwargs):
        raise RuntimeError("debug error")

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(broken_panel)

    request = rf.get("/")
    with pytest.raises(PanelRenderError):
        render_with_layout(request, TLayout, "partial.html")


def test_layouts_debug_errors_false_overrides_debug(rf, locmem_templates, settings):
    """LAYOUTS_DEBUG_ERRORS=False suppresses PanelRenderError even in DEBUG."""
    settings.DEBUG = True
    settings.DJ_LAYOUTS = {"DEBUG_ERRORS": False}
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'bad' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )
    on_error_called = []

    def broken_panel(request, **kwargs):
        raise RuntimeError("suppressed")

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(broken_panel)

        def on_panel_error(self, request, error):
            on_error_called.append(True)
            return ""

    request = rf.get("/")
    render_with_layout(request, TLayout, "partial.html")
    assert on_error_called == [True]


def test_layouts_debug_errors_true_overrides_production(rf, locmem_templates, settings):
    """LAYOUTS_DEBUG_ERRORS=True raises PanelRenderError even in production."""
    from dj_layouts.errors import PanelRenderError

    settings.DEBUG = False
    settings.DJ_LAYOUTS = {"DEBUG_ERRORS": True}
    locmem_templates(
        {
            "layouts/t.html": "{% load layouts %}{% panel 'bad' %}{% endpanel %}{% panel 'content' %}{% endpanel %}",
            "partial.html": "body",
        }
    )

    def broken_panel(request, **kwargs):
        raise RuntimeError("forced debug")

    class TLayout(Layout):
        template = "layouts/t.html"
        bad = Panel(broken_panel)

    request = rf.get("/")
    with pytest.raises(PanelRenderError):
        render_with_layout(request, TLayout, "partial.html")
