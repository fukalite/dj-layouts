from django import template
from django.utils.safestring import mark_safe

from dj_layouts.queues import add_script, add_style, add_to_queue


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


# ── Queue adding tags ─────────────────────────────────────────────────────────


class AddScriptNode(template.Node):
    def __init__(
        self,
        src_expr: template.base.FilterExpression | None = None,
        is_async: bool = False,
        is_deferred: bool = False,
        inline_nodes: template.NodeList | None = None,
    ) -> None:
        self.src_expr = src_expr
        self.is_async = is_async
        self.is_deferred = is_deferred
        self.inline_nodes = inline_nodes

    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        if self.inline_nodes is not None:
            content = self.inline_nodes.render(context).strip()
            add_script(request, inline=content)
        else:
            src = self.src_expr.resolve(context)  # type: ignore[union-attr]
            add_script(request, src, is_async=self.is_async, is_deferred=self.is_deferred)
        return ""


@register.tag("addscript")
def addscript_tag(
    parser: template.base.Parser, token: template.base.Token
) -> AddScriptNode:
    """
    Enqueue a script URL or inline script block::

        {% addscript "/static/js/chart.js" %}
        {% addscript "/static/js/chart.js" async %}
        {% addscript "/static/js/chart.js" defer %}
        {% addscript %}
          document.addEventListener('DOMContentLoaded', init);
        {% endaddscript %}
    """
    bits = token.split_contents()
    if len(bits) == 1:
        # Block form: {% addscript %}...{% endaddscript %}
        nodelist = parser.parse(("endaddscript",))
        parser.delete_first_token()
        return AddScriptNode(inline_nodes=nodelist)
    src_expr = parser.compile_filter(bits[1])
    is_async = "async" in bits[2:]
    is_deferred = "defer" in bits[2:]
    return AddScriptNode(src_expr=src_expr, is_async=is_async, is_deferred=is_deferred)


class AddStyleNode(template.Node):
    def __init__(
        self,
        href_expr: template.base.FilterExpression | None = None,
        media: str = "",
        inline_nodes: template.NodeList | None = None,
    ) -> None:
        self.href_expr = href_expr
        self.media = media
        self.inline_nodes = inline_nodes

    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        if self.inline_nodes is not None:
            content = self.inline_nodes.render(context).strip()
            add_style(request, inline=content)
        else:
            href = self.href_expr.resolve(context)  # type: ignore[union-attr]
            add_style(request, href, media=self.media)
        return ""


@register.tag("addstyle")
def addstyle_tag(
    parser: template.base.Parser, token: template.base.Token
) -> AddStyleNode:
    """
    Enqueue a stylesheet URL or inline style block::

        {% addstyle "/static/css/chart.css" %}
        {% addstyle "/static/css/chart.css" media="print" %}
        {% addstyle %}
          .chart { color: red; }
        {% endaddstyle %}
    """
    bits = token.split_contents()
    if len(bits) == 1:
        # Block form: {% addstyle %}...{% endaddstyle %}
        nodelist = parser.parse(("endaddstyle",))
        parser.delete_first_token()
        return AddStyleNode(inline_nodes=nodelist)
    href_expr = parser.compile_filter(bits[1])
    media = ""
    for bit in bits[2:]:
        if bit.startswith("media="):
            media = bit[len("media="):].strip("\"'")
    return AddStyleNode(href_expr=href_expr, media=media)


class EnqueueNode(template.Node):
    def __init__(self, queue_name: str, nodelist: template.NodeList) -> None:
        self.queue_name = queue_name
        self.nodelist = nodelist

    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        content = self.nodelist.render(context).strip()
        add_to_queue(request, self.queue_name, content)
        return ""


@register.tag("enqueue")
def enqueue_tag(
    parser: template.base.Parser, token: template.base.Token
) -> EnqueueNode:
    """
    Enqueue a block of content into a named RenderQueue::

        {% enqueue "head_extras" %}
        <meta name="robots" content="noindex">
        {% endenqueue %}
    """
    bits = token.split_contents()
    if len(bits) != 2:  # noqa: PLR2004
        raise template.TemplateSyntaxError(
            f"'{bits[0]}' tag requires exactly one argument (queue name)."
        )
    queue_name = bits[1].strip("\"'")
    nodelist = parser.parse(("endenqueue",))
    parser.delete_first_token()
    return EnqueueNode(queue_name, nodelist)


# ── Queue rendering tags ──────────────────────────────────────────────────────


class RenderScriptsNode(template.Node):
    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        queue = getattr(request, "layout_queues", {}).get("scripts")
        if queue is None or not queue._items:
            return ""
        return mark_safe(queue.render())  # noqa: S308


@register.tag("renderscripts")
def renderscripts_tag(
    parser: template.base.Parser, token: template.base.Token
) -> RenderScriptsNode:
    """Render all enqueued ``<script>`` tags. No-op if the queue is empty."""
    return RenderScriptsNode()


class RenderStylesNode(template.Node):
    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        queue = getattr(request, "layout_queues", {}).get("styles")
        if queue is None or not queue._items:
            return ""
        return mark_safe(queue.render())  # noqa: S308


@register.tag("renderstyles")
def renderstyles_tag(
    parser: template.base.Parser, token: template.base.Token
) -> RenderStylesNode:
    """Render all enqueued ``<link>``/``<style>`` tags. No-op if the queue is empty."""
    return RenderStylesNode()


class RenderQueueNode(template.Node):
    def __init__(self, queue_name: str) -> None:
        self.queue_name = queue_name

    def render(self, context: template.Context) -> str:
        request = context.get("request")
        if request is None:
            return ""
        queue = getattr(request, "layout_queues", {}).get(self.queue_name)
        if queue is None or not queue._items:
            return ""
        return mark_safe(queue.render())  # noqa: S308


@register.tag("renderqueue")
def renderqueue_tag(
    parser: template.base.Parser, token: template.base.Token
) -> RenderQueueNode:
    """
    Render a named queue via its configured template. No-op if empty::

        {% renderqueue "head_extras" %}
    """
    bits = token.split_contents()
    if len(bits) != 2:  # noqa: PLR2004
        raise template.TemplateSyntaxError(
            f"'{bits[0]}' tag requires exactly one argument (queue name)."
        )
    queue_name = bits[1].strip("\"'")
    return RenderQueueNode(queue_name)
