from django import template


register = template.Library()


class PanelNode(template.Node):
    def __init__(self, panel_name: str, fallback_nodes: template.NodeList) -> None:
        self.panel_name = panel_name
        self.fallback_nodes = fallback_nodes

    def render(self, context: template.Context) -> str:
        panels: dict[str, str] = context.get("_panels") or {}  # type: ignore[assignment]
        content = panels.get(self.panel_name, "")
        if content:
            return content
        return self.fallback_nodes.render(context)


@register.tag("panel")
def panel_tag(parser: template.base.Parser, token: template.base.Token) -> PanelNode:
    bits = token.split_contents()
    if len(bits) != 2:  # noqa: PLR2004
        raise template.TemplateSyntaxError(
            f"'{bits[0]}' tag requires exactly one argument (panel name)."
        )
    panel_name = bits[1].strip("\"'")
    fallback_nodes = parser.parse(("endpanel",))
    parser.delete_first_token()
    return PanelNode(panel_name, fallback_nodes)
