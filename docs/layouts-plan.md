# Django Layouts — Design Plan

> A view-composition pattern for Django, inspired by Zend Framework's layouts/views/view-helpers.

## The Core Idea

In standard Django, a base template defines structure and child templates fill blocks (top-down). **Layouts inverts this**: a view is primary — it returns its own content as a partial, and a Layout class wraps it, filling surrounding regions ("panels") by calling other views.

This gives you:

1. **HTMX-native** — views are partials by default; full pages are composed. Partial updates are free.
2. **Decoupled** — views never import each other; wiring happens at the Layout level only.
3. **Independently testable** — every panel is a real view you can hit with a test client.
4. **Independently cacheable** — per-panel caching with clear, explicit config.
5. **Progressive** — works without JS (full page render); better with HTMX or similar.
6. **Familiar** — decorators, views, templates. Just composed differently.

---

## Terminology

| Term                  | Definition                                                                                     |
| --------------------- | ---------------------------------------------------------------------------------------------- |
| **View**              | A Django view that returns partial HTML (its own content only)                                  |
| **Layout**            | A class that assembles a full page from panels + render queues                                  |
| **Panel**             | A named region in the layout, filled by a self-contained source config                         |
| **Render queue**      | An accumulator (scripts, styles, etc.) that collects items and renders them once, deduplicated  |
| **Partial detection** | Multi-strategy check for whether to skip the layout and return the raw partial                  |
| **Layout context**    | A layered dict available to all panels and the layout template                                  |

---

## API Surface

### Layout Class

All concerns for a panel (source, context, caching) are co-located in the `Panel()` declaration. No spreading config across multiple methods.

```python
from layouts import Layout, Panel, ScriptQueue, StyleQueue, RenderQueue, cache

class DefaultLayout(Layout):
    template = "layouts/default.html"

    # --- Panels: fully self-contained ---

    navigation = Panel(
        "core:navigation",
        cache=cache.per_user(timeout=300),
    )

    sidebar = Panel(
        render_sidebar,                              # Callable
        context={"limit": 3, "style": "compact"},
        cache=cache.per_user_per_path(timeout=60),
    )

    footer = Panel(
        "<p>© 2026 Acme</p>",                       # Static string
        cache=cache.sitewide(timeout=3600),
    )

    announcements = Panel(
        ["announcements:banner", "announcements:alerts"],  # Assembly
        join="",
        cache=cache.per_user(timeout=120),
    )

    recent_items = Panel(
        "items:item_list",
        context={"limit": 3},
    )

    # --- Render queues ---

    scripts = ScriptQueue()                          # First-class: knows how to render <script> tags
    styles = StyleQueue()                            # First-class: knows how to render <link>/<style> tags
    head_extras = RenderQueue(                       # Generic: for custom content (meta tags, etc.)
        template="layouts/_head_extras.html",
    )

    # --- Layout context: class-level defaults ---

    layout_context_defaults = {
        "site_name": "Intranet Sandbox",
        "nav_style": "horizontal",
    }

    # --- Hooks (optional, only for dynamic logic) ---

    def get_layout_context(self, request):
        """Extend layout context dynamically. Merged on top of class defaults."""
        return {"current_team": get_team(request.user)}

    def on_panel_error(self, request, panel_name, exc):
        """Handle panel failure. Return fallback HTML or re-raise."""
        return ""

    def get_template(self, request):
        """Override template selection dynamically."""
        return self.template
```

---

### Panel Sources

A Panel takes a `source` which can be any of:

| Source type | Example                    | Behaviour                                                      |
| ----------- | -------------------------- | -------------------------------------------------------------- |
| URL name    | `"core:navigation"`        | Resolve URL → call view with cloned GET request                |
| Callable    | `render_sidebar`           | Call `fn(request, **context)` → return `str` or `HttpResponse` |
| String      | `"<p>static</p>"`          | Render as-is (marked safe)                                     |
| List        | `["app:v1", func, "<hr>"]` | Render each item independently, concatenate with `join`        |
| None        | `None`                     | Empty — template default content fills in                      |

**List sources can mix types.** Each item in a list resolves independently using the same logic as a single source:

```python
Panel([
    "core:navigation",         # URL name
    render_custom_banner,      # Callable
    "<hr class='divider'>",    # Static string
    "announcements:alerts",    # URL name
], join="")
```

### Callable Return Types

A callable receives `(request, **context)` and can return:

| Return type    | Handling                      |
| -------------- | ----------------------------- |
| `HttpResponse` | Extract `.content.decode()`   |
| `str`          | Treated as HTML (marked safe) |

**A view IS a valid callable** — it takes a request and returns an HttpResponse. Works directly:

```python
sidebar = Panel(my_sidebar_view, context={"limit": 3})
```

**Dynamic routing within a callable** — no special return type needed. Just call the target view yourself:

```python
def dynamic_sidebar(request, **kwargs):
    if request.user.is_staff:
        return admin_sidebar(request, **kwargs)
    return public_sidebar(request, **kwargs)

sidebar = Panel(dynamic_sidebar)
```

If you need URL-based indirection (view isn't importable), a utility helper:

```python
from layouts import resolve_panel_source

def dynamic_sidebar(request, **kwargs):
    url_name = "admin:sidebar" if request.user.is_staff else "public:sidebar"
    return resolve_panel_source(request, url_name, **kwargs)
```

### Panel() Constructor

```python
Panel(
    source=None,               # URL name | callable | string | list | None  (positional)
    *,
    url_name: str = None,      # Explicit URL name — always calls reverse(), even without ":"
    literal: str = None,       # Explicit literal HTML — never passed to reverse()
    context: dict = None,      # Extra kwargs forwarded to the source view/callable
    cache: CacheConfig = None, # Caching config (use shortcuts)
    join: str = "",            # Separator when source is a list
)
```

Exactly one of `source`, `url_name=`, or `literal=` must be supplied. Mixing them raises `TypeError`.

**String source resolution rules:**

| Positional value | Behaviour |
|---|---|
| `"app:view_name"` | contains `:` → `reverse()`, `NoReverseMatch` propagates (no silent fallback) |
| `"plain text"` | no `:` → returned as literal HTML, `reverse()` never called |
| `""` | empty output, same as `None` |

**Escape hatches for edge cases:**

```python
Panel(url_name="home")             # reverse() a non-namespaced URL name (no ":" needed)
Panel(literal="text:with:colons")  # literal content that happens to contain ":"
```

`url_name=` and `literal=` work the same way on `resolve_panel_source()` directly.

### Panel context and URL kwargs — precedence

`Panel.context` kwargs are forwarded to the view as keyword arguments. When the source is a URL name, they are merged **on top of** URL-captured route parameters, so panel context wins:

```python
# URL: path("items/<int:pk>/", item_view, name="shop:item")
Panel("shop:item", context={"pk": 42})
# → item_view receives pk=42, regardless of what the URL captured
```

**This is intentional behaviour** — it lets you pin a panel to a specific object without building a custom URL. It also means that if a panel's `context` dict contains a key that clashes with a URL capture, the context value wins silently. Avoid duplicate keys unless you mean to override.

> **Warning:** Do not put user-supplied or untrusted values into `Panel.context`. Panel context is defined at class/decoration time and is a configuration mechanism, not a request-time parameter. For request-driven data, read from `request.layout_context` or pass values through the layout context system.

### Panel Priority Order

When multiple sources could fill a panel, resolution order is:

1. **View-level override** — passed via `@layout()` kwargs or `render_with_layout()`
2. **Layout class Panel() definition** — the default configuration
3. **Template default** — content between `{% panel "name" %}...{% endpanel %}` tags

---

### Decorator

```python
from layouts import layout

@layout(DefaultLayout)
def dashboard(request):
    return render(request, "dashboard/_partial.html", {"stats": get_stats()})
```

The view renders only its own content. The decorator intercepts the response and passes it to the Layout for full-page assembly — unless partial detection fires.

The class can also be referenced by dotted string to avoid circular imports (e.g. when `views.py` and `layouts.py` would otherwise import each other):

```python
@layout("myapp.DefaultLayout")
def dashboard(request):
    ...
```

The string is resolved lazily against the layout registry on first request. Both forms are equivalent at runtime.

**Per-view panel overrides:**

```python
@layout(DefaultLayout, panels={"sidebar": Panel("dashboard:custom_sidebar")})
def dashboard(request):
    ...
```

**Undecorated views are completely unaffected.** The system is entirely opt-in. Zero interference.

### Render Function (alternative to decorator)

For views that want explicit control without partial detection:

```python
from layouts import render_with_layout, add_script

def dashboard(request):
    add_script(request, "/static/js/dashboard.js")
    return render_with_layout(
        request, DefaultLayout,
        "dashboard/_partial.html", context,
        panels={"sidebar": None},
    )
```

Always renders the full layout. No partial detection. Supports panel overrides and render queues.

---

### Request Attributes — View Awareness

Views can introspect their rendering context via attributes set BEFORE the view executes:

```python
request.layout_role         # "main" | "panel" | (not set)
request.is_layout_partial   # True | False | (not set)
request.layout_context      # LayoutContext dict | (not set)
```

**`layout_role`:**

- `"main"` — this view is the primary content of a layout
- `"panel"` — this view is being called to fill a panel
- Not set — no layout system involved (undecorated view, behaves as today)

**`is_layout_partial`:**

- `True` — partial detection fired; no layout will wrap this output (it's going back as-is)
- `False` — the layout will assemble the full page around this output

**Usage:**

```python
@layout(DefaultLayout)
def item_list(request, limit=None, page=1):
    # Behaviour based on role
    if request.layout_role == "panel":
        limit = limit or 3

    # Behaviour based on partial mode
    if request.is_layout_partial:
        # Could skip expensive computation only needed for full page
        pass

    qs = Item.objects.all()
    if limit:
        items = qs[:limit]
        show_pagination = False
    else:
        paginator = Paginator(qs, 25)
        items = paginator.get_page(page)
        show_pagination = True

    return render(request, "items/_list.html", {
        "items": items, "show_pagination": show_pagination,
    })
```

**How it's set by the decorator:**

```python
def layout_wrapper(request, *args, **kwargs):
    is_partial = should_render_partial(request)
    request.layout_role = "main"
    request.is_layout_partial = is_partial

    response = view_func(request, *args, **kwargs)

    if is_partial:
        return response
    return layout.render(request, response.content)
```

**How it's set for panel views:**

```python
def _call_panel_view(request, view_func, kwargs):
    panel_request = clone_request_as_get(request)
    panel_request.layout_role = "panel"
    panel_request.is_layout_partial = False
    return view_func(panel_request, **kwargs)
```

**Safe @layout on panel views:** The decorator checks `layout_role` and becomes a no-op:

```python
if getattr(request, 'layout_role', None) == "panel":
    return view_func(request, *args, **kwargs)  # Already in a layout — skip
```

This is part of the public API, not a private underscore hack.

---

### Template Tags

**Layout template:**

```html
{% load layouts %}
<!DOCTYPE html>
<html>
  <head>
    {% renderstyles %}
    {% panel "styles" %}
      <link rel="stylesheet" href="/static/base.css" />
    {% endpanel %}
    {% renderqueue "head_extras" %}
  </head>
  <body>
    <nav>{% panel "navigation" %}Default nav{% endpanel %}</nav>
    <main>{% panel "content" %}{% endpanel %}</main>
    <aside>{% panel "sidebar" %}{% endpanel %}</aside>
    <footer>
      {% panel "footer" %}
        <p>Default footer</p>
      {% endpanel %}
    </footer>
    {% renderscripts %}
  </body>
</html>
```

- `{% panel "name" %}...default...{% endpanel %}` — renders panel output; uses fallback if source is None/empty
- `{% renderscripts %}` — outputs accumulated script items (first-class, knows `<script>` rendering)
- `{% renderstyles %}` — outputs accumulated style items (first-class, knows `<link>`/`<style>` rendering)
- `{% renderqueue "name" %}` — outputs a generic queue through its configured template

Layout templates support `{% extends %}`, `{% block %}`, `{% load %}` — full Django template features. View templates render in a separate pass with their own context.

**From view templates (adding to queues):**

```html
{% load layouts %}

{# Script URLs: #}
{% addscript "/static/js/chart.js" %}
{% addscript "/static/js/analytics.js" async %}
{% addscript "/static/js/vendor.js" defer %}

{# Inline script blocks: #}
{% addscript %}
document.addEventListener('DOMContentLoaded', function() {
    initChart();
});
{% endaddscript %}

{# Style URLs: #}
{% addstyle "/static/css/chart.css" %}
{% addstyle "/static/css/print.css" media="print" %}

{# Inline style blocks: #}
{% addstyle %}
.chart { color: red; }
{% endaddstyle %}

{# Generic queue (escape hatch): #}
{% enqueue "head_extras" %}
<meta name="robots" content="noindex">
{% endenqueue %}
```

**Implementation: Context variables.** The rendering engine assembles panel outputs and queue contents into the template context before rendering the layout template:

```python
context = {
    "_panels": {
        "navigation": "<nav>Home | About</nav>",
        "content": "<h1>Dashboard</h1>...",
        "sidebar": "<aside>...</aside>",
    },
    "_scripts": [ScriptItem(src="/static/js/chart.js"), ...],
    "_styles": [StyleItem(href="/static/css/chart.css"), ...],
    "_queues": {
        "head_extras": ["<meta ...>", ...],
    },
    "request": request,
}
```

The `{% panel %}` tag reads from `context["_panels"]`. Standard Django template context — testable, inspectable, no magic.

**Clear demarcation:** View templates render with view context (normal Django context). Layout templates render with layout context (panel outputs are pre-rendered HTML strings). Two separate render passes.

---

### Partial Detection (multi-strategy)

```python
# settings.py
LAYOUTS_PARTIAL_DETECTORS = [
    "layouts.detection.htmx_detector",
    "layouts.detection.query_param_detector",
]
```

If **any** configured detector returns True, the layout is skipped and the partial is returned directly.

**Built-in detectors:**

```python
def htmx_detector(request):
    """Skip layout for HTMX partial requests (not boosted)."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-Boosted") != "true"
    )

def query_param_detector(request):
    """Skip layout when ?_partial=1 — useful for testing."""
    return request.GET.get("_partial") == "1"

def never_detector(request):
    """Never skip layout."""
    return False
```

Multiple detectors active simultaneously. Tests use `?_partial=1`, real clients use HTMX headers. Write your own by implementing `(request) -> bool`.

---

### Panel Caching

Uses Django's cache framework (`django.core.cache`) behind the scenes. Standard `caches[config.backend].get()`/`.set()` calls against the configured backend.

**Cache shortcuts:**

```python
from layouts import cache

cache.sitewide(timeout=3600)             # Same for everyone
cache.per_user(timeout=300)              # Vary on user.id
cache.per_path(timeout=300)              # Vary on request.path
cache.per_user_per_path(timeout=60)      # Vary on both
cache.per_session(timeout=600)           # Vary on session key

# Full control:
cache.custom(
    timeout=120,
    vary_on=["user.id", "GET.theme", "COOKIES.locale"],
    backend="redis",
    key_prefix="nav",
)
```

**CacheConfig:**

```python
@dataclass
class CacheConfig:
    timeout: int
    vary_on: list[str] = field(default_factory=list)
    backend: str = "default"
    key_prefix: str = ""
    key_func: Callable | None = None       # Custom key generation
    stale_ttl: int = 0                     # Reserved for future stale-while-revalidate
    refresh_func: Callable | None = None   # Reserved hook for background refresh
```

**v1 behaviour — simple and predictable:**
- **Cache miss** → render panel, store with `timeout`
- **Cache hit** → serve cached content
- **Expired** → re-render, re-cache
- **`invalidate_panel_cache()`** → deletes cache key(s)

No stale logic, no dual-TTL bookkeeping, no race conditions. The `stale_ttl` and `refresh_func` fields are present on the dataclass but are no-ops in v1 — the interface is stable so stale-while-revalidate can be activated later without API changes.

**Future `refresh_func` signature (for when stale support is added):**

```python
def my_refresh(request, layout_name, panel_name, stale_content):
    """Called when stale content is being served. Trigger background refresh here."""
    ...
```

**Cache invalidation:**

```python
from layouts import invalidate_panel_cache

invalidate_panel_cache("default", "navigation", vary={"user.id": user.id})
```

**No Vary headers.** Panel caching is purely server-side. It has nothing to do with HTTP caching. If you need `Vary` headers for CDNs or Django's full-page cache middleware, manage them at the view/middleware level as normal — orthogonal to layouts.

---

### Layout Context

A dict available to all panels and the layout template. Pre-populated by the layout, mutable by the main view, **read-only for panels**.

**Three merge levels (later wins):**

| Priority    | Source                                    | When set                       |
| ----------- | ----------------------------------------- | ------------------------------ |
| 1 (lowest)  | `Layout.layout_context_defaults = {...}`  | Class definition               |
| 2           | `Layout.get_layout_context(request)`      | At render start, before panels |
| 3 (highest) | `request.layout_context[key] = val`       | During main view execution     |

```python
# Layout class sets defaults:
class DefaultLayout(Layout):
    layout_context_defaults = {"site_name": "Intranet", "nav_style": "horizontal"}

    def get_layout_context(self, request):
        return {"current_team": get_team(request.user)}

# Main view — full read/write access:
@layout(DefaultLayout)
def dashboard(request):
    ctx = request.layout_context

    # Already populated with merged defaults + get_layout_context():
    print(ctx["site_name"])         # "Intranet Sandbox"
    print(ctx["current_team"])      # Team object

    # Override:
    ctx["nav_style"] = "vertical"

    # Add:
    ctx["page_title"] = "Dashboard"

    # Remove:
    del ctx["optional_thing"]
    ctx.pop("something", None)      # Safe remove

    return render(request, "dashboard/_partial.html", {...})

# Panel view — read-only access:
def sidebar(request, **kwargs):
    team = request.layout_context.get("current_team")    # OK
    nav = request.layout_context["nav_style"]             # "vertical" (overridden by view)
    request.layout_context["foo"] = "bar"                 # Raises TypeError
    return render(request, "sidebar/_partial.html", {"team": team})
```

**Implementation:** `LayoutContext` is a `dict` subclass. The rendering engine populates it with merged defaults, then the main view can freely read, write, and delete entries. Before passing the request to panel views, the engine calls `freeze()` which returns a `FrozenLayoutContext` — same data, but `__setitem__`, `__delitem__`, `pop`, `update`, `clear`, and `setdefault` all raise `TypeError("layout_context is read-only in panel views")`.

This eliminates order-of-execution issues: the main view is the only writer, panels only read.

---

### Render Queues

**First-class queues** for scripts and styles, plus a **generic queue** for anything else.

#### ScriptQueue and StyleQueue

Purpose-built, clear API. The layout knows how to render `<script>` and `<link>`/`<style>` tags without user-supplied templates.

**From views:**

```python
from layouts import add_script, add_style

@layout(DefaultLayout)
def chart_widget(request):
    # URL-based scripts
    add_script(request, "/static/js/chart.js")
    add_script(request, "/static/js/analytics.js", is_async=True)
    add_script(request, "/static/js/vendor.js", is_deferred=True)

    # Inline script
    add_script(request, inline="document.addEventListener('DOMContentLoaded', init)")

    # URL-based styles
    add_style(request, "/static/css/chart.css")
    add_style(request, "/static/css/print.css", media="print")

    # Inline style
    add_style(request, inline=".chart { color: red; }")

    return render(request, "widgets/_chart.html", {...})
```

**From templates:**

```html
{% load layouts %}

{% addscript "/static/js/chart.js" %}
{% addscript "/static/js/analytics.js" async %}
{% addscript "/static/js/vendor.js" defer %}

{% addscript %}
document.addEventListener('DOMContentLoaded', function() {
    initChart();
});
{% endaddscript %}

{% addstyle "/static/css/chart.css" %}

{% addstyle %}
.chart { color: red; }
{% endaddstyle %}
```

**Internal representation — frozen dataclasses (hashable by default, dedup is free):**

```python
@dataclass(frozen=True)
class ScriptItem:
    src: str | None = None
    inline: str | None = None
    is_async: bool = False
    is_deferred: bool = False
    type: str = ""

@dataclass(frozen=True)
class StyleItem:
    href: str | None = None
    inline: str | None = None
    media: str = ""
```

**Rendering:** `{% renderscripts %}` and `{% renderstyles %}` know how to output the correct HTML — `<script src="...">`, `<script async src="...">`, `<script>...inline...</script>`, `<link rel="stylesheet" href="...">`, `<style>...inline...</style>`, etc. No user-supplied template needed.

#### Generic RenderQueue

For custom content that doesn't fit scripts or styles — meta tags, modal containers, toast roots, etc.

```python
class DefaultLayout(Layout):
    head_extras = RenderQueue(template="layouts/_head_extras.html")
```

```python
from layouts import add_to_queue

add_to_queue(request, "head_extras", '<meta name="robots" content="noindex">')
```

Or from templates:

```html
{% enqueue "head_extras" %}
<meta name="robots" content="noindex">
{% endenqueue %}
```

Rendered via `{% renderqueue "head_extras" %}` using the configured template.

#### Deduplication

All queues (script, style, generic) deduplicate by hash. Strings are hashable natively. Frozen dataclasses are hashable by default. No custom key logic, no conditional paths.

```python
class BaseQueue:
    def __init__(self):
        self._items: list = []
        self._seen: set = set()

    def add(self, item):
        if item not in self._seen:
            self._seen.add(item)
            self._items.append(item)
```

Duplicate `/static/js/chart.js` from three different panels → added once.

---

### Async Rendering

Async out of the box. The rendering engine uses `asyncio.gather()` to render all panels concurrently.

**Rendering order guarantee:**

1. Main view executes → produces content + modifies layout context + enqueues items
2. Layout context is frozen (read-only from this point)
3. All panel views execute **concurrently** (`asyncio.gather()`)
4. Layout template renders synchronously with all outputs assembled

| Concern                  | Handling                                                               |
| ------------------------ | ---------------------------------------------------------------------- |
| Sync panel views         | Auto-wrapped with `sync_to_async` (detected via `iscoroutinefunction`) |
| ORM access               | Use async ORM (`aget`, `afilter`) or let sync wrapping handle it       |
| Layout context integrity | Main view writes, then frozen; panels only read                        |
| Render queue ordering    | Insertion order preserved per panel; interleaved in definition order    |
| Error isolation          | `return_exceptions=True` — one failure doesn't crash others            |
| Template rendering       | `render_to_string` called directly (CPU-bound; `sync_to_async` would add thread overhead for no I/O benefit) |
| WSGI / sync deployments  | Use `@layout` / `render_with_layout` — zero async overhead. Users choose explicitly; there is no auto-detection. |

---

### @layout on Panel Views

Safe and encouraged. A view can be both a standalone page AND a panel:

```python
@layout(DefaultLayout)
def recent_items(request, limit=10):
    items = get_items()[:limit]
    return render(request, "items/_list.html", {"items": items})
```

- **Called as a URL** (user navigates to `/items/`) → `@layout` applies, full page with layout
- **Called as a panel** → `request.layout_role == "panel"` → decorator becomes a no-op, partial returned

Panel context passes kwargs to adjust behaviour:

```python
recent_items = Panel("items:item_list", context={"limit": 3})
```

---

### Pagination Pattern

Same view handles both standalone and panel modes:

```python
@layout(DefaultLayout)
def item_list(request, limit=None, page=1):
    qs = Item.objects.all()
    if limit:
        items = qs[:limit]
        show_pagination = False
    else:
        paginator = Paginator(qs, 25)
        items = paginator.get_page(page)
        show_pagination = True
    return render(request, "items/_list.html", {
        "items": items,
        "show_pagination": show_pagination,
    })
```

- As a panel: `Panel("items:item_list", context={"limit": 3})` → top 3, no pagination
- As a standalone page: full paginated list
- HTMX pagination: partial detection returns just the list fragment for in-place updates

---

### GET-Only Panel Views

Panels always receive a cloned request with:

- `method = "GET"`
- `POST` / `FILES` stripped (empty)
- Everything else preserved: `user`, `session`, `cookies`, `resolver_match`, `path`, layout context, queues

This ensures panels can never trigger mutations and avoids CSRF/middleware complications.

---

### TemplateResponse Handling

Django's `TemplateResponse` delays rendering until the response passes through middleware. Layouts uses **eager rendering**: if the main view returns a `TemplateResponse`, it is force-rendered immediately inside the decorator/render function.

```python
response = view_func(request, *args, **kwargs)
if hasattr(response, 'render'):
    response.render()  # Force render now
main_content = response.content.decode()
```

**Implications:**
- The view's output is locked in at decorator time — what the view returned is exactly what goes into the `content` panel
- Middleware that modifies `TemplateResponse` context/template will NOT affect the main view's output (already rendered)
- Middleware WILL still affect the final layout response (which is a plain `HttpResponse`)
- Panel views are called internally and never pass through middleware anyway — eager rendering is natural for them
- Predictable and debuggable: no deferred render chains, no ordering surprises

---

### Class-Based Views — `LayoutMixin`

For CBVs, `LayoutMixin` is the equivalent of `@layout`. It follows the same conventions as `WagtailLayoutMixin` so both feel like the same system:

```python
from layouts import LayoutMixin
from django.views.generic import TemplateView

class DashboardView(LayoutMixin, TemplateView):
    layout_class = DefaultLayout
    template_name = "dashboard/_partial.html"  # Partial — no {% extends %}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = get_stats()
        return context
```

`layout_class` accepts either a class or a dotted string (same as the decorator). The mixin overrides `dispatch()` to apply layout assembly after the view's normal response is produced. Partial detection and per-view panel overrides work identically to the decorator:

```python
class DashboardView(LayoutMixin, TemplateView):
    layout_class = "myapp.DefaultLayout"          # string ref — avoids circular imports
    layout_panels = {"sidebar": Panel("dashboard:custom_sidebar")}  # per-view override
    template_name = "dashboard/_partial.html"
```

The string ref is resolved lazily against the registry on first request, same as the decorator.

---

### Wagtail Integration

```python
from layouts import WagtailLayoutMixin

class BlogPage(WagtailLayoutMixin, Page):
    layout_class = BlogLayout
    template = "blog/_content.html"  # Partial — no {% extends %}

    def get_context(self, request):
        context = super().get_context(request)
        context["posts"] = self.get_children().live()
        return context
```

The mixin overrides `serve()`:

1. Checks partial detection → if triggered, renders page template as partial (normal Wagtail behaviour)
2. Otherwise: renders page template as partial → passes to Layout for full-page assembly

**Issues & considerations:**

- Wagtail pages traditionally `{% extends "base.html" %}`. With layouts they render as partials instead — this is a mental model shift
- Preview mode (`request.is_preview`) should probably skip/simplify the layout
- Migration path: existing pages keep template inheritance, new pages opt into the mixin
- StreamField blocks already render as partials — natural fit
- Each Page subclass can specify its own `layout_class`

---

## Comparison with Existing Approaches

| Approach                         | How Layouts differs                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| Django `{% block %}` inheritance | Top-down: base defines, child fills. Layouts is inverted: view is primary.          |
| `{% include %}` / inclusion tags | Runs in parent context, no view isolation, no independent caching.                  |
| django-components                | Template-level composition, not view-level. No independent URL addressability.      |
| Turbo Frames (Hotwire)           | Client-driven decomposition. Layouts is server-driven with HTMX as optimisation.    |
| Zend Framework layouts           | Direct inspiration. This is the Django equivalent with async and per-panel caching. |

---

## Error Propagation

### Error scenarios

1. **Panel view raises an exception** (ORM error, import error, bug)
2. **Panel view returns a non-200 status** (403, 404, redirect)
3. **Panel source resolution fails** (URL name doesn't resolve, callable not found)
4. **Panel view times out** (relevant in async — one panel hangs)

### PanelError dataclass

The error hook receives a structured object with everything needed for per-error-code, per-panel, and per-source filtering:

```python
@dataclass
class PanelError:
    panel_name: str                        # Name of the panel that failed
    exception: Exception                   # The original exception
    status_code: int | None                # None for unhandled exceptions; HTTP code for non-200
    source: str | Callable | None          # The panel source that failed

    @property
    def is_http_error(self) -> bool:
        return self.status_code is not None
```

### The hook

```python
class DefaultLayout(Layout):
    def on_panel_error(self, request, error: PanelError) -> str:
        # Per status code:
        if error.status_code == 404:
            return ""  # Silently hide
        if error.status_code == 403:
            return '<p class="text-muted">Not available</p>'

        # Per panel:
        if error.panel_name == "sidebar":
            return render_to_string("layouts/_sidebar_fallback.html")

        # Per source view:
        if error.source == "dashboard:widget":
            return "<p>Widget temporarily unavailable</p>"

        # Default: empty
        return ""
```

### Behaviour by mode

**DEBUG mode (or `LAYOUTS_DEBUG_ERRORS = True`):**
- The hook is bypassed entirely
- A `PanelRenderError` is raised with full context: panel name, layout class, source, original traceback
- Django's standard yellow error page shows with clear attribution
- Non-200 responses and resolution failures are also raised as `PanelRenderError`

**Production (DEBUG=False):**
- The exception is always logged automatically via `logging.getLogger("layouts")` at ERROR level, including panel name, layout class, source, and traceback — this is the framework's responsibility, not the hook's
- `on_panel_error` is called and controls what renders in place of the failed panel
- Default implementation returns `""` (empty panel)

### Non-200 response handling

**In the `@layout` decorator:**
- **Non-200 responses** (301/302 redirects, 404, 403, 5xx) are passed through to the caller unchanged. The decorator does not attempt to wrap them in a layout.
- **`StreamingHttpResponse`** is also passed through unchanged.
- Only `200` responses with a rendered body are assembled into the layout.

**In panel views (sources called by the engine):**
- Panel views that return non-200 responses are treated as errors. The `on_panel_error` hook is called (or `PanelRenderError` raised in debug mode).
- **301/302 redirects:** A panel cannot redirect the whole page. Treated as error, hook called.
- **403 Forbidden:** Common pattern — return empty string from `on_panel_error` to silently hide the panel from unauthorised users.
- **404 Not Found / 5xx:** Hook can return fallback content or empty string.

### Async error isolation

`asyncio.gather(return_exceptions=True)` means one panel failure doesn't prevent others from completing. Failed panels get the hook treatment; successful panels render normally. The page still assembles — it just has empty/fallback content where the failed panel was.

### Panel source resolution failures

These are configuration errors (bad URL name, missing view, etc.):
- In DEBUG: raise immediately with a clear message ("Panel 'sidebar' references URL name 'dashboard:missing' which could not be resolved")
- In production: same as runtime error (log + hook)

---

## Design Decisions: Resolved, Pending Documentation

These are not open questions — the decisions are made. They need clear documentation when the package is written.

### Registry and autodiscovery

Layout classes register themselves in a global registry via `__init_subclass__` (or metaclass — to be decided in `base.py`). Each installed app's `layouts.py` is auto-imported at startup via `AppConfig.ready()` + `autodiscover_modules("layouts")`, triggering registration as a side effect — identical to Django admin's `admin.py` autodiscovery.

The registry enables:
- Lazy string resolution for `@layout("myapp.DefaultLayout")` and `layout_class = "myapp.DefaultLayout"`
- System checks (e.g. reference to a layout that was never registered)
- Future tooling (`manage.py layouts list`, debug pages)

String format is `"<app_label>.<ClassName>"` — consistent with Django conventions (`AUTH_USER_MODEL`, `DEFAULT_AUTO_FIELD`). Passing a class directly always works and bypasses string resolution entirely.

### CBV support

`LayoutMixin` is included in v1. It follows the same `layout_class` / `layout_panels` attribute convention as `WagtailLayoutMixin` so both feel like one coherent system. Implementation is ~30 lines wrapping `dispatch()` to call `render_with_layout()` on the view's response.

### Middleware interaction

Panel views are called internally, not through the middleware stack. **This is a documented limitation, not a bug.** The implication list for users:

- Auth/session: fine — already on the request object
- CSRF: irrelevant — panels are always GET
- Rate limiting middleware: won't count individual panel calls
- Audit logging middleware: won't log panel rendering
- Any custom middleware: does not run for panels

Document this prominently in the "Middleware and panels" explanation page and in the reference for `Panel`. The panel middleware pipeline (a narrower opt-in pipeline for per-panel concerns) is deferred — see "Deferred to Future Versions".

### Security model

The decision is `@panel_only` (opt-in, documented). Document this in a dedicated security guide:

- Panel views with URL patterns are public endpoints by default — document that views must apply their own auth checks (`@login_required` etc.) just like any other view
- `@panel_only` is the escape hatch for views that should never be hit directly (private data panels, structurally broken standalone)
- `@panel_only` and `@layout` are mutually exclusive — combining them raises `TypeError` at decoration time
- Partial detection headers (`HX-Request`, `?_partial=1`) do not grant panel access — `@panel_only` still returns 403

### Layout inheritance

v1 decision: support basic Python inheritance (override panels, override template, `super()` for `get_layout_context`). No panel removal support — "use a different base layout" is the answer. Document that inherited panels still require matching `{% panel "name" %}` tags in the child template.

**`__init_subclass__` for panel collection and registration.** It fires at the end of class body execution with full access to the completed class and its MRO — exactly what we need. A metaclass would only be necessary if we needed to intercept attribute assignment *during* class creation (e.g. via a custom `__prepare__` namespace), which we don't. `__init_subclass__` also avoids metaclass conflicts if a user's class hierarchy already has a metaclass.

---

## Settings Reference

```python
# All optional — the system works with zero configuration

LAYOUTS_PARTIAL_DETECTORS = [
    "layouts.detection.never_detector",  # Default: never skip layout — explicit opt-in for HTMX etc.
]

LAYOUTS_CACHE_ENABLED = True          # False disables all panel caching
LAYOUTS_CACHE_BACKEND = "default"     # Default Django cache backend to use
LAYOUTS_DEBUG_ERRORS = None           # None = follow DEBUG; True/False = override
```

---

## File Structure

```
src/layouts/
    __init__.py           # Public API exports: Layout, Panel, LayoutMixin, WagtailLayoutMixin,
                          # layout, panel_only, render_with_layout,
                          # add_script, add_style, add_to_queue, cache
    apps.py               # LayoutsConfig (AppConfig + autodiscovery)
    base.py               # Layout base class + registry
    panels.py             # Panel class + resolution logic
    queues.py             # ScriptQueue, StyleQueue, RenderQueue, ScriptItem, StyleItem
    cache.py              # CacheConfig, shortcuts, invalidation
    decorators.py         # @layout decorator, @panel_only decorator
    mixins.py             # LayoutMixin (CBV)
    errors.py             # PanelError, PanelRenderError
    rendering.py          # render_with_layout, async engine
    detection.py          # Partial detection strategies
    context.py            # LayoutContext, FrozenLayoutContext
    request_utils.py      # clone_request_as_get, resolve_panel_source
    wagtail.py            # WagtailLayoutMixin (conditional)
    autodiscover.py       # Find + load layouts.py from installed apps
    templatetags/
        layouts.py        # {% panel %}, {% endpanel %}, {% addscript %}, {% addstyle %},
                          # {% enqueue %}, {% renderscripts %}, {% renderstyles %},
                          # {% renderqueue %}
    templates/
        layouts/
            _error.html
    tests/
        __init__.py
        conftest.py
        test_base.py
        test_panels.py
        test_queues.py
        test_cache.py
        test_decorators.py
        test_rendering.py
        test_detection.py
        test_context.py
        test_templatetags.py
        test_mixins.py
        test_wagtail.py
        test_async.py

docs/layouts-phases/      # Per-phase implementation plans (agent-readable)
    00-overview.md
    01-sync-core.md
    02-async.md
    03-queues.md
    04-caching.md
    05-partial-detection.md
    06-wagtail.md

# When extracted as a standalone package:
docs/
    conf.py               # Sphinx + MyST config
    index.md
    getting-started/
        installation.md
        first-layout.md       # 5-minute tutorial
        migrating.md          # From template inheritance
    how-to/
        defining-panels.md
        caching-panels.md
        partial-detection.md  # HTMX integration
        scripts-styles.md
        render-queues.md
        panel-only.md
        async-panels.md
        cbvs.md               # Using LayoutMixin
        wagtail.md
        layout-inheritance.md
        testing.md
    explanation/
        why-layouts.md        # The inversion explained
        partial-detection.md  # How it works and its limits
        layout-context.md     # Mutable vs frozen
        async-rendering.md    # Concurrency model
        middleware.md         # What runs, what doesn't
        security.md           # Panel view security model
        comparison.md         # vs. fragments, HTMX partials, etc.
    reference/
        layout-class.md
        panel.md
        decorators.md
        mixins.md             # LayoutMixin
        render-with-layout.md
        queue-functions.md
        queue-classes.md
        cache.md
        context.md
        errors.md
        template-tags.md
        settings.md
        wagtail-mixin.md
        registry.md
    changelog/
        index.md
```

---

## Implementation Phases

Work is broken into six phases, each independently shippable. See [`docs/layouts-phases/`](./layouts-phases/) for the full breakdown.

| Phase | Name | Depends on |
|---|---|---|
| [1](./layouts-phases/01-sync-core.md) | Synchronous core | — |
| [2](./layouts-phases/02-async.md) | Async rendering | Phase 1 |
| [3](./layouts-phases/03-queues.md) | Render queues | Phase 2 |
| [4](./layouts-phases/04-caching.md) | Panel caching | Phase 2 |
| [5](./layouts-phases/05-partial-detection.md) | Partial detection + LayoutMixin | Phase 1 |
| [6](./layouts-phases/06-wagtail.md) | Wagtail + layout inheritance | Phase 1 |

Phases 3–6 are independent of each other once Phase 2 is done.

---

## Key Design Decisions (Summary)

| Decision                 | Choice                                           | Rationale                                   |
| ------------------------ | ------------------------------------------------ | ------------------------------------------- |
| Layout definition        | Class with co-located Panel configs               | Readable, overridable, inheritable          |
| Registry                 | Global, populated by `__init_subclass__`          | Enables string refs and system checks      |
| Autodiscovery            | `layouts.py` per app, via `AppConfig.ready()`     | Same pattern as Django admin               |
| Decorator string ref     | `@layout("app.LayoutClass")` lazy-resolved        | Avoids circular imports                    |
| CBV support              | `LayoutMixin` with `layout_class` attribute       | Mirrors `WagtailLayoutMixin`, same conventions |
| Panel config style       | All in `Panel()` constructor                      | No scavenger hunt across methods            |
| Panel sources            | URL name, callable, string, list, None            | Maximum flexibility                         |
| Callable returns         | `HttpResponse` or `str`                           | A view IS a callable — just works           |
| List items               | Each can be any source type (mixed)               | Consistent resolution logic                 |
| Template tag             | `{% panel %}` (not "slot")                        | Avoids design-system clash                  |
| Template tag impl        | Context variables (Option A)                      | Standard Django, testable, no magic         |
| Layout templates         | Full Django template features                     | Extends, blocks, tags all work              |
| View/layout demarcation  | Separate render passes                            | Clear mental model                          |
| TemplateResponse         | Eager rendering                                   | Predictable, debuggable, async-compatible   |
| Partial detection        | Multi-strategy (any fires)                        | Flexible, testable                          |
| Request attributes       | `layout_role` + `is_layout_partial`               | Public API, `is_` for booleans             |
| @layout on panel views   | Safe via `layout_role` check                      | Views reusable in both contexts             |
| Layout context           | Dict on request; mutable for main, frozen for panels | No order-of-execution issues            |
| Script/style queues      | First-class `ScriptQueue`/`StyleQueue`            | Clear API for the 90% case                  |
| Generic queues           | `RenderQueue` with user template                  | Escape hatch for custom content             |
| Queue dedup              | Hash-based (frozen dataclasses)                   | Simple, fast, no custom key logic           |
| Async                    | Out of the box, sync auto-wrapped                 | Modern Django, no extra work for users      |
| Caching                  | Django cache framework, simple miss/hit/expired   | Predictable v1, stale hooks reserved        |
| Cache shortcuts          | `cache.sitewide()`, `cache.per_user()`, etc.      | One-liners for common cases                 |
| Stale cache              | No-op in v1; `stale_ttl`/`refresh_func` reserved  | Interface stable for future enhancement     |
| Vary headers             | Not set by panel caching                          | Panel cache is server-side only             |
| Panel HTTP method        | Always GET (cloned request)                       | No mutations, no CSRF                       |
| Error hook               | `on_panel_error(request, PanelError)`             | Filterable by code, panel, source           |
| Error logging            | Framework always logs; hook controls rendering    | Separation of concerns                      |
| DEBUG errors             | Bypass hook, raise `PanelRenderError`             | Standard Django yellow page                 |
| Panel-only views         | `@panel_only` decorator (opt-in)                  | Explicit protection for sensitive panels    |
| Middleware               | Panels bypass middleware; document clearly         | Future: optional panel middleware pipeline  |
| Undecorated views        | Completely unaffected                             | Opt-in only                                 |
| Package boundary         | Zero project imports                              | Extractable from day one                    |

---

## Deferred to Future Versions

Items explicitly scoped out of v1. The v1 API is designed so these can be added as backwards-compatible enhancements.

### Stale-while-revalidate caching

The `CacheConfig` dataclass reserves `stale_ttl` and `refresh_func` fields (no-ops in v1). When activated, a panel whose cache entry has expired within `stale_ttl` would return the stale content immediately and trigger a background refresh via `refresh_func`. Requires careful handling of thundering herd, race conditions, and the new Django Tasks framework could be a natural backend for the refresh job.

### RenderQueue priority buckets

Adding `prepend()` / `add()` / `append()` (or `priority="early"|"normal"|"late"`) to give 3 guaranteed ordering buckets. Per-panel insertion order interleaved by panel-definition order is already deterministic in v1, and panel ordering in the Layout class body gives explicit control. Priority buckets add API surface to `add_script`, `add_style`, template tags, and their interaction with bare dict/string items in `RenderQueue` is awkward. Revisit if real-world use reveals ordering pain.

### Panel middleware pipeline

Panels bypass Django middleware entirely (they're internal function calls, not HTTP requests). A lightweight "panel middleware" concept could allow users to define a narrow pipeline (GET-only, no response streaming) for audit logging, per-panel rate limiting, per-panel auth checks, etc. The interface would be simpler than Django's full middleware.

### Signals / observability hooks

Django signals (`panel_rendered`, `layout_assembled`, `cache_miss`, `cache_hit`) for monitoring and observability. Useful for dashboards, APM integration, and debugging. The extension point should be designed even if the signals aren't emitted in v1.

### Panel removal in inheritance

When subclassing a Layout, there's no clean way to *remove* a parent's panel (as opposed to overriding it). Options include a `Panel.REMOVED` sentinel or `sidebar = None` with special semantics. For v1, "use a different layout" is the answer if you don't want a panel.

### Unrendered panel warnings

If a Layout template doesn't contain a `{% panel "name" %}` tag for a declared panel, the panel executes but its output is silently discarded. A system check or runtime warning could catch this mismatch. Needs template introspection, which is non-trivial.

### Nested layouts

A panel's callable could use `render_with_layout` with a *different* layout, producing nested chrome. `@layout` is already safe (no-ops when `layout_role == "panel"`), but `render_with_layout` is explicit and should work. Needs documentation and testing for edge cases (context isolation, queue merging vs. separation, error propagation through nesting levels).

### Native async cache backends

Django 6.0's async cache methods (`aget`, `aset`) are `sync_to_async` wrappers. When a truly async cache backend ships (Django core or third-party), the layouts caching layer should detect and use it natively for better performance. No code changes needed in v1 — `await cache.aget()` already works correctly with either implementation.

### Testing utilities

Purpose-built test helpers:
- `assert_panel_rendered(response, "navigation", contains="...")` — verify a specific panel's output
- `assert_partial_response(response)` — confirm no layout wrapper was applied
- Layout rendering in tests without a full request cycle (unit-test a Layout class directly)

### Performance benchmarking suite

A benchmark suite to quantify:
- Overhead of layout assembly vs vanilla Django template inheritance
- Impact of async vs sync panel rendering
- Cache hit ratio impact on response times
- Memory overhead of request cloning for panels
