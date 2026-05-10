import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from dj_layouts.base import Layout, _registry
from dj_layouts.decorators import layout, panel_only
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


@pytest.fixture()
def simple_layout(settings, locmem_templates):
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


# ── @layout decorator ─────────────────────────────────────────────────────────


def test_layout_decorator_wraps_response(rf, simple_layout):
    @layout(simple_layout)
    def my_view(request):
        return HttpResponse("<h1>Hello</h1>")

    request = rf.get("/")
    response = my_view(request)
    assert b"LAYOUT:" in response.content
    assert b"<h1>Hello</h1>" in response.content


def test_layout_decorator_sets_layout_role_main(rf, simple_layout):
    role_seen = []

    @layout(simple_layout)
    def my_view(request):
        role_seen.append(request.layout_role)
        return HttpResponse("")

    rf.get("/")
    request = rf.get("/")
    my_view(request)
    assert role_seen == ["main"]


def test_layout_decorator_sets_is_layout_partial_false(rf, simple_layout):
    partial_seen = []

    @layout(simple_layout)
    def my_view(request):
        partial_seen.append(request.is_layout_partial)
        return HttpResponse("")

    request = rf.get("/")
    my_view(request)
    assert partial_seen == [False]


def test_layout_decorator_noop_when_role_is_panel(rf, simple_layout):
    """@layout must be a no-op when the request is already in panel role."""
    call_count = [0]

    @layout(simple_layout)
    def my_view(request):
        call_count[0] += 1
        return HttpResponse("panel-content")

    request = rf.get("/")
    request.layout_role = "panel"
    response = my_view(request)
    # Response returned as-is, no layout wrapping
    assert response.content == b"panel-content"


def test_layout_decorator_accepts_dotted_string(rf, simple_layout):
    # Register simple_layout under a known key
    key = next(k for k, v in _registry.items() if v is simple_layout)

    @layout(key)
    def my_view(request):
        return HttpResponse("ok")

    request = rf.get("/")
    response = my_view(request)
    assert b"LAYOUT:" in response.content


def test_layout_decorator_panel_override(rf, locmem_templates):
    locmem_templates(
        {
            "layouts/override.html": (
                "{% load layouts %}"
                "{% panel 'sidebar' %}default-sidebar{% endpanel %}"
                "{% panel 'content' %}{% endpanel %}"
            ),
        }
    )

    class OverrideLayout(Layout):
        template = "layouts/override.html"
        sidebar = Panel("<p>class-sidebar</p>")

    @layout(OverrideLayout, panels={"sidebar": Panel("<p>view-sidebar</p>")})
    def my_view(request):
        return HttpResponse("<main>content</main>")

    request = rf.get("/")
    response = my_view(request)
    assert b"view-sidebar" in response.content
    assert b"class-sidebar" not in response.content


# ── @panel_only decorator ─────────────────────────────────────────────────────


def test_panel_only_allows_panel_role(rf):
    @panel_only
    def my_panel(request):
        return HttpResponse("panel-html")

    request = rf.get("/")
    request.layout_role = "panel"
    response = my_panel(request)
    assert response.status_code == 200
    assert response.content == b"panel-html"


def test_panel_only_returns_403_when_called_directly(rf):
    @panel_only
    def my_panel(request):
        return HttpResponse("panel-html")

    request = rf.get("/")
    response = my_panel(request)
    assert response.status_code == 403


def test_panel_only_returns_403_when_role_is_main(rf):
    @panel_only
    def my_panel(request):
        return HttpResponse("panel-html")

    request = rf.get("/")
    request.layout_role = "main"
    response = my_panel(request)
    assert response.status_code == 403


def test_panel_only_with_layout_raises_type_error():
    with pytest.raises(TypeError):

        class SomeLayout(Layout):
            template = "layouts/t.html"

        @layout(SomeLayout)
        @panel_only
        def bad_view(request):
            return HttpResponse("")


# ── @layout — layout_context available in view ────────────────────────────────


def test_layout_decorator_layout_context_set_before_view(rf, locmem_templates):
    """layout_context must be set on request before the wrapped view executes."""
    locmem_templates(
        {"layouts/simple.html": "{% load layouts %}{% panel 'content' %}{% endpanel %}"}
    )

    class TLayout(Layout):
        template = "layouts/simple.html"
        layout_context_defaults = {"site": "Intranet"}

    ctx_seen = {}

    @layout(TLayout)
    def my_view(request):
        ctx_seen["ctx"] = getattr(request, "layout_context", None)
        return HttpResponse("")

    request = rf.get("/")
    my_view(request)
    assert ctx_seen["ctx"] is not None
    assert ctx_seen["ctx"]["site"] == "Intranet"


# ── @layout — non-wrappable response pass-through ────────────────────────────


def test_layout_decorator_passes_through_redirect(rf, simple_layout):
    from django.http import HttpResponseRedirect

    @layout(simple_layout)
    def my_view(request):
        return HttpResponseRedirect("/other/")

    request = rf.get("/")
    response = my_view(request)
    assert response.status_code == 302
    assert response["Location"] == "/other/"


def test_layout_decorator_passes_through_404(rf, simple_layout):
    from django.http import HttpResponseNotFound

    @layout(simple_layout)
    def my_view(request):
        return HttpResponseNotFound()

    request = rf.get("/")
    response = my_view(request)
    assert response.status_code == 404


def test_layout_decorator_passes_through_streaming_response(rf, simple_layout):
    from django.http import StreamingHttpResponse

    @layout(simple_layout)
    def my_view(request):
        return StreamingHttpResponse(iter([b"stream"]))

    request = rf.get("/")
    response = my_view(request)
    assert isinstance(response, StreamingHttpResponse)
