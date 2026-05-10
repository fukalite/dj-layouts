# Getting Started

This guide walks you from a fresh Django project to a working layout with a content view and a sidebar panel.

## Requirements

- Python 3.11+
- Django 4.2+

## Installation

```bash
pip install dj-layouts
```

## Add to `INSTALLED_APPS`

```python
# settings.py
INSTALLED_APPS = [
    ...
    "dj_layouts",
]
```

That's all the configuration required. Autodiscovery of `layouts.py` modules starts automatically via `AppConfig.ready()`.

## Step 1 — Create a Layout class

Create `myapp/layouts.py`. Any `Layout` subclass in a `layouts.py` file is automatically discovered and registered.

```python
# myapp/layouts.py
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "myapp/layout.html"

    # Declare panels as class attributes.
    # "myapp:sidebar" is a namespaced URL name — resolved via reverse().
    sidebar = Panel("myapp:sidebar")
```

`Layout` subclasses **must** declare a `template` attribute; you get a `TypeError` at class definition time if you forget.

## Step 2 — Write the layout template

```html+django
{# myapp/templates/myapp/layout.html #}
{% load layouts %}
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ page_title|default:"My Site" }}</title>
</head>
<body>
  <header><h1>My Site</h1></header>

  <div class="layout">
    <aside>
      {# Fallback content shown when the sidebar panel is empty or missing #}
      {% panel "sidebar" %}<p>No sidebar available.</p>{% endpanel %}
    </aside>

    <main>
      {# "content" is the main view's output — always available #}
      {% panel "content" %}{% endpanel %}
    </main>
  </div>
</body>
</html>
```

`{% panel "name" %}...{% endpanel %}` renders the named panel's HTML if it produced output, otherwise renders the fallback content between the tags.

## Step 3 — Write your views

```python
# myapp/views.py
from django.http import HttpResponse
from dj_layouts import layout, panel_only

@layout("myapp.DefaultLayout")
def homepage(request):
    """Main content view — renders inside DefaultLayout."""
    return HttpResponse("<h1>Welcome!</h1><p>Hello, world.</p>")

@panel_only
def sidebar(request):
    """Panel view — only callable as a panel (returns 403 otherwise)."""
    return HttpResponse("<nav><a href='/'>Home</a></nav>")
```

`@layout("myapp.DefaultLayout")` — the dotted string is resolved lazily from the registry, which avoids circular imports between `views.py` and `layouts.py`.

`@panel_only` — marks a view as panel-only. Calling it directly (e.g. via the browser) returns 403.

## Step 4 — Wire up URLs

```python
# myapp/urls.py
from django.urls import path
from . import views

app_name = "myapp"

urlpatterns = [
    path("", views.homepage, name="home"),
    path("_panels/sidebar/", views.sidebar, name="sidebar"),
]
```

!!! tip "Panel URL conventions"
    Prefixing panel URLs with `_panels/` is just a convention. There's nothing magic about the prefix. Panel views still appear in `urlpatterns` so Django can resolve them — they just return 403 when hit directly.

## Step 5 — Try it

Start your dev server and visit `/`. You'll see:

- The layout template rendered as a full page
- The sidebar panel's HTML in the `<aside>` slot
- Your homepage content in the `<main>` slot

If you visit `/_panels/sidebar/` directly you'll get a **403 Forbidden** — because it's decorated with `@panel_only`.

## Next steps

- **Use `@async_layout`** for concurrent panel rendering on ASGI — see [Async](async.md).
- **Add layout context** (page title, current user data, etc.) — see [Layout Context](layout-context.md).
- **Add a render queue** for per-panel scripts/styles — see [Render Queues](render-queues.md).
- **Understand the full Panel API** — see [Panels](panels.md).
