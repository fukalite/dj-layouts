import pytest
from django.http import HttpResponse

from dj_layouts.context import LayoutContext
from dj_layouts.panels import Panel, resolve_panel_source


# ── None source ───────────────────────────────────────────────────────────────


def test_none_source_returns_empty(request_with_context):
    assert resolve_panel_source(request_with_context, None) == ""


# ── Plain string source ───────────────────────────────────────────────────────


def test_plain_string_returned_as_is(request_with_context):
    html = "<p>static footer</p>"
    assert resolve_panel_source(request_with_context, html) == html


def test_plain_html_with_no_colon_returned_as_is(request_with_context):
    html = "<nav>Home | About</nav>"
    assert resolve_panel_source(request_with_context, html) == html


def test_empty_string_source_returns_empty(request_with_context):
    assert resolve_panel_source(request_with_context, "") == ""


# ── Callable source ───────────────────────────────────────────────────────────


def test_callable_returning_string(request_with_context):
    def my_panel(request, **kwargs):
        return "<aside>Sidebar</aside>"

    result = resolve_panel_source(request_with_context, my_panel)
    assert result == "<aside>Sidebar</aside>"


def test_callable_returning_http_response(request_with_context):
    def my_panel(request, **kwargs):
        return HttpResponse("<aside>via response</aside>")

    result = resolve_panel_source(request_with_context, my_panel)
    assert result == "<aside>via response</aside>"


def test_callable_receives_context(request_with_context):
    def my_panel(request, **kwargs):
        return f"<p>limit={kwargs.get('limit', 0)}</p>"

    result = resolve_panel_source(request_with_context, my_panel, limit=5)
    assert result == "<p>limit=5</p>"


def test_callable_receives_get_method_request(request_with_context):
    """Panel callables always receive a GET request (cloned by the assembly loop)."""
    method_seen = []

    def my_panel(request, **kwargs):
        method_seen.append(request.method)
        return ""

    resolve_panel_source(request_with_context, my_panel)
    # resolve_panel_source itself doesn't clone; cloning happens upstream in _assemble_layout.
    # Called directly here with a GET request, so method is GET.
    assert method_seen == ["GET"]


# ── List source ───────────────────────────────────────────────────────────────


def test_list_concatenates_items(request_with_context):
    def part_a(request, **kwargs):
        return "<a>"

    result = resolve_panel_source(request_with_context, ["<b>", part_a, None])
    assert result == "<b><a>"


def test_list_empty_returns_empty(request_with_context):
    assert resolve_panel_source(request_with_context, []) == ""


def test_list_with_none_items(request_with_context):
    result = resolve_panel_source(request_with_context, [None, None])
    assert result == ""


def test_list_join_separator(request_with_context):
    """_join kwarg is used as separator when source is a list."""
    result = resolve_panel_source(request_with_context, ["<a>", "<b>"], _join=" | ")
    assert result == "<a> | <b>"


def test_unsupported_source_type_raises(request_with_context):
    with pytest.raises(TypeError, match="Unsupported panel source type"):
        resolve_panel_source(request_with_context, 12345)


# ── URL name source ───────────────────────────────────────────────────────────


urlpatterns_for_test = None  # filled below


def _nav_view(request):
    return HttpResponse("<nav>Navigation</nav>")


def _ctx_view(request, **kwargs):
    limit = request.GET.get("limit", kwargs.get("limit", "?"))
    return HttpResponse(f"<p>items={limit}</p>")




def test_url_name_calls_view(rf, url_conf):
    import tests.test_panels as mod

    mod.urlpatterns = url_conf
    req = rf.get("/")
    req.layout_context = LayoutContext({})
    # Non-namespaced name → use url_name= kwarg to force reverse()
    result = resolve_panel_source(req, url_name="test_nav")
    assert "<nav>" in result


def test_url_name_without_colon_is_literal(request_with_context):
    """A bare word (no colon) is never treated as a URL name — always literal."""
    # 'test_nav' has no namespace separator; should return the string unchanged
    result = resolve_panel_source(request_with_context, "test_nav")
    assert result == "test_nav"


def test_namespaced_url_not_found_raises(rf):
    """Strings with ':' always attempt reverse(); NoReverseMatch propagates (no fallback)."""
    req = rf.get("/")
    req.layout_context = LayoutContext({})
    from django.urls import NoReverseMatch

    with pytest.raises(NoReverseMatch):
        resolve_panel_source(req, "app:nonexistent_view_xyz")


def test_url_name_clone_is_get(rf, url_conf):
    import tests.test_panels as mod

    mod.urlpatterns = url_conf
    methods_seen = []

    def spy_view(request):
        methods_seen.append(request.method)
        return HttpResponse("")

    from django.urls import path

    mod.urlpatterns = [path("spy/", spy_view, name="test_spy")]

    # resolve_panel_source passes the request as-is; cloning is the caller's responsibility.
    # In normal use _assemble_layout pre-clones to GET before calling resolve_panel_source.
    req = rf.get("/")
    req.layout_context = LayoutContext({})
    resolve_panel_source(req, url_name="test_spy")
    assert methods_seen == ["GET"]


# ── url_name= kwarg (explicit URL, no ":" required) ──────────────────────────


def test_url_name_kwarg_resolves_bare_name(rf, url_conf):
    """url_name= allows non-namespaced URL names to be resolved."""
    import tests.test_panels as mod

    mod.urlpatterns = url_conf
    req = rf.get("/")
    req.layout_context = LayoutContext({})
    result = resolve_panel_source(req, url_name="test_nav")
    assert "<nav>" in result


def test_url_name_kwarg_raises_on_missing(rf):
    """url_name= propagates NoReverseMatch (no silent fallback)."""
    from django.urls import NoReverseMatch

    req = rf.get("/")
    req.layout_context = LayoutContext({})
    with pytest.raises(NoReverseMatch):
        resolve_panel_source(req, url_name="totally_nonexistent_xyz")


# ── literal= kwarg (explicit HTML, never reversed) ───────────────────────────


def test_literal_kwarg_with_colon_not_reversed(request_with_context):
    """literal= is always returned as-is, even when it contains ':'."""
    result = resolve_panel_source(request_with_context, literal="app:fake_url_name")
    assert result == "app:fake_url_name"


def test_literal_kwarg_returns_html(request_with_context):
    html = "<footer>© 2025</footer>"
    result = resolve_panel_source(request_with_context, literal=html)
    assert result == html


# ── Panel descriptor ──────────────────────────────────────────────────────────


def test_panel_stores_source():
    p = Panel("core:navigation")
    assert p.source == "core:navigation"


def test_panel_url_name_kwarg():
    p = Panel(url_name="home")
    assert p.source == "home"
    assert p._source_kind == "url_name"


def test_panel_literal_kwarg():
    p = Panel(literal="app:not_a_url")
    assert p.source == "app:not_a_url"
    assert p._source_kind == "literal"


def test_panel_positional_source_kind_is_auto():
    p = Panel("core:nav")
    assert p._source_kind == "auto"


def test_panel_mutual_exclusion_raises():
    with pytest.raises(TypeError):
        Panel("core:nav", url_name="home")

    with pytest.raises(TypeError):
        Panel("text", literal="also text")

    with pytest.raises(TypeError):
        Panel(url_name="home", literal="text")


def test_panel_stores_context():
    p = Panel(None, context={"limit": 5})
    assert p.context == {"limit": 5}


def test_panel_stores_join():
    p = Panel([], join="\n")
    assert p.join == "\n"


def test_panel_default_join_is_empty_string():
    p = Panel(None)
    assert p.join == ""


def test_panel_cache_stored():
    p = Panel(None, cache="some-cache-config")
    assert p.cache == "some-cache-config"
