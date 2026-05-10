# dj-layouts

**dj-layouts** is a Django layout composition library that inverts the normal template-inheritance model.

Instead of a base template with `{% block %}` holes that child templates fill, your views return their own content as HTML partials. A `Layout` class assembles the full page by calling other views as named **panels** — concurrently under ASGI.

## The mental model shift

| Classic Django | dj-layouts |
|---|---|
| Base template owns the page structure | `Layout` class owns the page structure |
| Child template fills `{% block content %}` | Content view returns its own partial HTML |
| Sidebar is a template include | Sidebar is a panel — an independent view |
| All template logic in one render pass | Panels render concurrently via `asyncio.gather` |
| Base and child tightly coupled | Views never import each other |

The key insight: **views are HTMX-native partials by default**. A view decorated with `@layout` renders the full page when called directly; if called as a panel it just returns its partial. Your view code stays the same either way.

## Minimal complete example

**`myapp/layouts.py`**

```python
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel("myapp:sidebar")
```

**`myapp/views.py`**

```python
from django.http import HttpResponse
from dj_layouts import layout, panel_only

@layout("myapp.DefaultLayout")
def homepage(request):
    return HttpResponse("<h1>Welcome!</h1>")

@panel_only
def sidebar(request):
    return HttpResponse("<nav>Links here</nav>")
```

**`myapp/templates/myapp/layout.html`**

```html+django
{% load layouts %}
<!doctype html>
<html>
<head><title>My Site</title></head>
<body>
  <aside>{% panel "sidebar" %}<p>No sidebar.</p>{% endpanel %}</aside>
  <main>{% panel "content" %}{% endpanel %}</main>
</body>
</html>
```

That's it. `homepage` renders the full page. The sidebar runs as a separate view, independently testable, and — on ASGI with `@async_layout` — runs concurrently with any other panels.

## Key benefits

- **Views are independent.** Panel views never import each other; wiring happens at the Layout level.
- **HTMX-ready.** Every view is already a partial. HTMX can target panel views directly.
- **Concurrent rendering.** Under ASGI, all panels run via `asyncio.gather` — no serial waterfall.
- **Independent testability.** Test each panel view in isolation, no full-page setup needed.
- **Graceful errors.** A failing panel shows a fallback; the rest of the page still renders.

## Where to go next

| Topic | Page |
|---|---|
| First layout, first view | [Getting Started](getting-started.md) |
| How it all fits together | [Concepts](concepts.md) |
| `Layout` class reference | [Layouts](layouts.md) |
| `Panel` sources and options | [Panels](panels.md) |
| Script/style queues | [Render Queues](render-queues.md) |
| Layout context | [Layout Context](layout-context.md) |
| `@layout`, `@panel_only`, `@async_layout` | [Decorators](decorators.md) |
| Concurrent panel rendering | [Async](async.md) |
| Error hooks and debug mode | [Error Handling](error-handling.md) |
| Common patterns | [Patterns](patterns.md) |
| Security considerations | [Security](security.md) |
| `request.layout_*` attributes | [Request Attributes](request-attributes.md) |
| `DJ_LAYOUTS` settings dict | [Settings](settings.md) |
