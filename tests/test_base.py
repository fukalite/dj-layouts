import pytest
from django.test import RequestFactory

from dj_layouts.base import Layout, _registry
from dj_layouts.panels import Panel


@pytest.fixture(autouse=True)
def clear_registry():
    """Isolate each test from leftover registrations."""
    snapshot = dict(_registry)
    yield
    _registry.clear()
    _registry.update(snapshot)


@pytest.fixture()
def rf():
    return RequestFactory()


# ── Registration ──────────────────────────────────────────────────────────────


def test_layout_subclass_is_registered():
    class MyLayout(Layout):
        template = "layouts/my.html"

    key = f"{MyLayout.__module__.split('.')[0]}.MyLayout"
    assert _registry.get(key) is MyLayout or any(
        v is MyLayout for v in _registry.values()
    )


def test_layout_registered_by_app_label_and_class_name():
    class SomeLayout(Layout):
        template = "layouts/some.html"

    # Registry key uses the class name; app_label derived from module
    assert any(k.endswith(".SomeLayout") for k in _registry)


def test_abstract_base_not_registered():
    # Layout itself should NOT be in the registry
    assert not any(v is Layout for v in _registry.values())


def test_layout_lookup_by_dotted_string():
    class LookupalbeLayout(Layout):
        template = "layouts/x.html"

    key = next(k for k, v in _registry.items() if v is LookupalbeLayout)
    assert Layout.resolve(key) is LookupalbeLayout


def test_layout_resolve_unknown_string_raises():
    with pytest.raises(KeyError):
        Layout.resolve("nonexistent.Layout")


# ── Attributes ───────────────────────────────────────────────────────────────


def test_layout_template_required():
    with pytest.raises(TypeError):

        class NoTemplateLayout(Layout):
            pass


def test_layout_panels_collected():
    p = Panel(None)

    class PaneledLayout(Layout):
        template = "layouts/t.html"
        nav = p

    assert PaneledLayout._panels["nav"] is p


def test_layout_collects_panel_subclass():
    """_panels collection uses isinstance, so Panel subclasses are recognised."""

    class CustomPanel(Panel):
        pass

    p = CustomPanel(None)

    class SubPaneledLayout(Layout):
        template = "layouts/t.html"
        sidebar = p

    assert SubPaneledLayout._panels["sidebar"] is p


def test_layout_context_defaults_used():
    class CtxLayout(Layout):
        template = "layouts/t.html"
        layout_context_defaults = {"site": "Acme"}

    assert CtxLayout.layout_context_defaults == {"site": "Acme"}


# ── get_layout_context ────────────────────────────────────────────────────────


def test_get_layout_context_default_returns_empty_dict(rf):
    class SimpleLayout(Layout):
        template = "layouts/t.html"

    instance = SimpleLayout()
    request = rf.get("/")
    assert instance.get_layout_context(request) == {}


def test_get_layout_context_can_be_overridden(rf):
    class RichLayout(Layout):
        template = "layouts/t.html"

        def get_layout_context(self, request):
            return {"user": "bob"}

    instance = RichLayout()
    request = rf.get("/")
    assert instance.get_layout_context(request) == {"user": "bob"}


# ── get_template ──────────────────────────────────────────────────────────────


def test_get_template_returns_class_attribute(rf):
    class TLayout(Layout):
        template = "layouts/t.html"

    instance = TLayout()
    request = rf.get("/")
    assert instance.get_template(request) == "layouts/t.html"


def test_get_template_can_be_overridden(rf):
    class DynLayout(Layout):
        template = "layouts/default.html"

        def get_template(self, request):
            return "layouts/alt.html"

    instance = DynLayout()
    request = rf.get("/")
    assert instance.get_template(request) == "layouts/alt.html"


# ── error_template ────────────────────────────────────────────────────────────


def test_error_template_default():
    class TLayout(Layout):
        template = "layouts/t.html"

    assert TLayout().error_template == "layouts/error.html"


def test_error_template_can_be_overridden():
    class TLayout(Layout):
        template = "layouts/t.html"
        error_template = "myapp/custom_error.html"

    assert TLayout().error_template == "myapp/custom_error.html"


def test_on_panel_error_uses_error_template(rf, locmem_templates):
    """on_panel_error always renders error_template (not gated on DEBUG)."""
    locmem_templates(
        {
            "myapp/panel_error.html": "ERR:{{ error.panel_name }}",
        }
    )
    from dj_layouts.errors import PanelError

    class TLayout(Layout):
        template = "layouts/t.html"
        error_template = "myapp/panel_error.html"

    error = PanelError("nav", "core:nav", ValueError("boom"), "tb")
    result = TLayout().on_panel_error(rf.get("/"), error)
    assert result == "ERR:nav"


def test_on_panel_error_renders_in_production(rf, locmem_templates, settings):
    """on_panel_error renders error_template in production (DEBUG=False) — the common path."""
    settings.DEBUG = False
    locmem_templates({"layouts/error.html": "PANEL-ERROR:{{ error.panel_name }}"})
    from dj_layouts.errors import PanelError

    class TLayout(Layout):
        template = "layouts/t.html"

    error = PanelError("sidebar", "core:sidebar", RuntimeError("fail"), "tb")
    result = TLayout().on_panel_error(rf.get("/"), error)
    assert result == "PANEL-ERROR:sidebar"


def test_on_panel_error_returns_empty_when_template_missing(
    rf, locmem_templates, settings
):
    """If error_template doesn't exist, on_panel_error returns '' rather than crashing."""
    settings.DEBUG = False
    locmem_templates({})
    from dj_layouts.errors import PanelError

    class TLayout(Layout):
        template = "layouts/t.html"
        error_template = "does/not/exist.html"

    error = PanelError("nav", None, RuntimeError("fail"), "tb")
    result = TLayout().on_panel_error(rf.get("/"), error)
    assert result == ""
