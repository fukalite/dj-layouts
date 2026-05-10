import pytest
from django.template import Context, Template


@pytest.fixture()
def render_panel(locmem_templates):
    """Helper: configure a layout template and render it with given panel context."""

    def _render(template_str: str, panels: dict) -> str:
        locmem_templates({"layouts/t.html": template_str})
        t = Template(template_str)
        return t.render(Context({"_panels": panels}))

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
