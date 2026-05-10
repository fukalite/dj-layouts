# Concepts

This page explains the core mental model behind dj-layouts: what each piece is, how they relate, and how they differ from standard Django template inheritance.

## The problem with `{% block %}`

Classic Django template inheritance looks like this:

```
base.html        (owns the page structure, has {% block %} holes)
  └── page.html  (fills the holes with content)
```

This works fine until you want the sidebar to show something dynamic — user info, recent posts, contextual navigation. You end up passing sidebar data from every view that uses `base.html`, or you reach for template tags that query the database in the template layer.

Panels solve this by moving each region into its own view.

## The dj-layouts mental model

```
Layout class        (owns the page structure, declares which panels to render)
  ├── content view  (your main view — returns its HTML partial)
  ├── sidebar view  (independent view — returns sidebar HTML)
  └── header view   (independent view — returns header HTML)
```

Each panel is a fully independent Django view. It has its own URL, its own tests, its own caching surface (future). The Layout class wires them together without any of them importing each other.

## Core concepts

### Layout

A `Layout` is a Python class (subclass of `dj_layouts.Layout`) that declares:

- **`template`** — the layout template path (required)
- **Panel attributes** — `Panel(...)` instances assigned as class attributes
- **`layout_context_defaults`** — default variables available in the template and to the content view
- Overridable methods: `get_layout_context()`, `get_template()`, `on_panel_error()`

```python
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {"site_name": "My App"}

    sidebar = Panel("myapp:sidebar")
    footer  = Panel("myapp:footer")
```

Subclassing `Layout` automatically registers the class under the key `"myapp.DefaultLayout"`. Registration happens at class definition time, and `layouts.py` modules in every installed app are autodiscovered on startup.

### Panel

A `Panel` is a configuration object that describes how to render one named region in the layout. It is **not** a view itself — it's the wiring between the Layout and the view that produces the content.

```python
Panel("myapp:sidebar")          # URL name → reversed and called as a view
Panel("myapp:item", context={"pk": 5})  # with extra kwargs
Panel("<p>Static HTML</p>")     # literal string → returned as-is
Panel(url_name="home")          # explicit URL name (no ":" needed)
Panel(None)                     # empty — template fallback is used
```

See [Panels](panels.md) for the full source-type reference.

### Content view

The "content" panel is special: it's always the output of your main view — the one decorated with `@layout`. Every other panel is a *separate* view called by the layout engine.

```python
@layout("myapp.DefaultLayout")
def homepage(request):
    return HttpResponse("<h1>Welcome!</h1>")
```

The content view's HTML becomes `{% panel "content" %}` in the layout template.

### Panel view

Any Django view can be a panel view. There are no special base classes or mixins required. A panel view just returns an `HttpResponse` (or a string) containing its HTML fragment.

```python
def sidebar(request):
    items = MenuItem.objects.all()
    return render(request, "myapp/sidebar.html", {"items": items})
```

Panel views receive a **cloned, GET-only** request. `request.user`, `request.session`, and cookies are preserved, but `POST` data is cleared and the view never goes through middleware again. See [Security](security.md) for implications.

Use `@panel_only` to prevent a panel view from being called directly:

```python
@panel_only
def sidebar(request):
    ...
```

### Layout context

Layout context is a shared dict that flows from the Layout to the content view and is readable (but not writable) in panel views. Use it for data that multiple panels need — the current user's display name, active navigation item, page title, etc.

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {"site_name": "My App"}

    def get_layout_context(self, request):
        return {"current_user_name": request.user.get_full_name()}
```

The content view can also write to `request.layout_context` before the layout template renders:

```python
@layout("myapp.DefaultLayout")
def homepage(request):
    request.layout_context["page_title"] = "Home"
    return HttpResponse(...)
```

See [Layout Context](layout-context.md) for the full merge order and read/write rules.

### Render queues

Render queues let panel views enqueue scripts and stylesheets that are then rendered once in the layout template, deduplicated, and in a guaranteed order (content view first, then panels in definition order).

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()
    styles  = StyleQueue()
```

See [Render Queues](render-queues.md) for the full API.

## Comparison with standard approaches

| | Classic `{% block %}` | Template tags | dj-layouts |
|---|---|---|---|
| Page structure | In base template | In base template | In Layout class |
| Sidebar data | Passed from every view | Queried in template tag | Sidebar is its own view |
| Views coupled? | Tightly (base ↔ child) | Somewhat (tag lives in template) | Not at all |
| Testability | Test full page | Test tag in isolation | Test each view in isolation |
| Concurrent rendering | No | No | Yes (ASGI + `@async_layout`) |
| HTMX partials | Manual duplication | Manual | Built-in — views are already partials |
| Error isolation | One error breaks the page | One error breaks the page | Per-panel error handling |

## Request lifecycle

Here is what happens when a request hits a `@layout`-decorated view:

```
Browser → Django → @layout wrapper
    1. Sets request.layout_role = "main"
    2. Sets request.is_layout_partial = False
    3. Builds layout_context, sets request.layout_context
    4. Calls your content view → gets HTML partial
    5. For each Panel in the Layout:
         a. Clones request (method=GET, POST cleared, layout_role="panel")
         b. Freezes layout_context on the clone
         c. Calls the panel's source view/callable/literal
    6. (Under @async_layout: steps 5a–5c run concurrently via asyncio.gather)
    7. Renders the layout template with all panel outputs
    8. Returns full-page HttpResponse
```
