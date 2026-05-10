import pytest

from dj_layouts.base import Layout, _registry
from dj_layouts.panels import Panel


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


# ── Inheritance ────────────────────────────────────────────────────────────────


def test_subclass_inherits_parent_panels():
    p = Panel(None)

    class ParentLayout(Layout):
        template = "layouts/parent.html"
        nav = p

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"

    assert ChildLayout._panels["nav"] is p


def test_subclass_panel_override_shadows_parent():
    p_parent = Panel(None)
    p_child = Panel(None)

    class ParentLayout(Layout):
        template = "layouts/parent.html"
        nav = p_parent

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"
        nav = p_child

    assert ChildLayout._panels["nav"] is p_child
    assert ParentLayout._panels["nav"] is p_parent


def test_subclass_inherits_parent_queue_configs():
    from dj_layouts.queues import ScriptQueue

    q = ScriptQueue()

    class ParentLayout(Layout):
        template = "layouts/parent.html"
        scripts = q

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"

    assert ChildLayout._queue_configs["scripts"] is q


def test_subclass_registered_separately():
    class ParentLayout(Layout):
        template = "layouts/parent.html"

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"

    parent_key = next(k for k, v in _registry.items() if v is ParentLayout)
    child_key = next(k for k, v in _registry.items() if v is ChildLayout)
    assert parent_key != child_key
    assert parent_key.endswith(".ParentLayout")
    assert child_key.endswith(".ChildLayout")


def test_get_layout_context_super_merges_parent_and_child(rf):
    class ParentLayout(Layout):
        template = "layouts/parent.html"

        def get_layout_context(self, request):
            return {"from_parent": True}

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"

        def get_layout_context(self, request):
            ctx = super().get_layout_context(request)
            ctx["from_child"] = True
            return ctx

    result = ChildLayout().get_layout_context(rf.get("/"))
    assert result == {"from_parent": True, "from_child": True}


def test_on_panel_error_can_be_overridden_without_super(rf):
    from dj_layouts.errors import PanelError

    class CustomLayout(Layout):
        template = "layouts/t.html"

        def on_panel_error(self, request, error):
            return "custom-error"

    error = PanelError("nav", None, ValueError("boom"), "tb")
    result = CustomLayout().on_panel_error(rf.get("/"), error)
    assert result == "custom-error"


def test_three_level_inheritance_chain():
    from dj_layouts.queues import ScriptQueue

    p1 = Panel(None)
    p2 = Panel(None)
    q = ScriptQueue()

    class GrandparentLayout(Layout):
        template = "layouts/grandparent.html"
        nav = p1
        scripts = q

    class ParentLayout(GrandparentLayout):
        template = "layouts/parent.html"
        sidebar = p2

    class ChildLayout(ParentLayout):
        template = "layouts/child.html"

    # Child inherits from all ancestors
    assert ChildLayout._panels["nav"] is p1
    assert ChildLayout._panels["sidebar"] is p2
    assert ChildLayout._queue_configs["scripts"] is q

    # All three levels are registered with distinct keys
    assert any(v is GrandparentLayout for v in _registry.values())
    assert any(v is ParentLayout for v in _registry.values())
    assert any(v is ChildLayout for v in _registry.values())
    gp_key = next(k for k, v in _registry.items() if v is GrandparentLayout)
    p_key = next(k for k, v in _registry.items() if v is ParentLayout)
    c_key = next(k for k, v in _registry.items() if v is ChildLayout)
    assert len({gp_key, p_key, c_key}) == 3
