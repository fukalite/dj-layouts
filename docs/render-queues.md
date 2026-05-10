# Render Queues

Render queues let panel views enqueue scripts, stylesheets, or arbitrary HTML fragments. The layout template then renders each queue exactly once, deduplicated, in a guaranteed order.

## Why render queues?

Without queues, if three panels each need the same JavaScript library, you either include it three times (bad) or hard-code it in the layout template regardless of which panels are active (wasteful). Render queues solve this:

- Each panel enqueues what it needs
- Duplicates are automatically removed (by exact match)
- Output order is deterministic: content view first, then panels in definition order
- Template tags produce no output themselves — they only enqueue

## Setup

Declare queue instances as **class attributes** on your Layout:

```python
from dj_layouts import Layout
from dj_layouts.queues import ScriptQueue, StyleQueue

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()
    styles  = StyleQueue()
```

!!! warning "Queues must be explicitly declared"
    Queues do not appear automatically. Each `ScriptQueue()` / `StyleQueue()` declared as a class attribute is a **config object** (factory). Each incoming request gets its own fresh set of queue instances — the class-level object is never mutated.

The attribute name (`scripts`, `styles`) is the queue name used in template tags.

## Queue types

### `ScriptQueue`

Collects `<script>` tags or inline script blocks. Rendered with `{% renderscripts %}` or `{% renderqueue "scripts" %}`.

Conventional name: `scripts` (to match `{% renderscripts %}`).

### `StyleQueue`

Collects `<link rel="stylesheet">` tags or inline style blocks. Rendered with `{% renderstyles %}` or `{% renderqueue "styles" %}`.

Conventional name: `styles` (to match `{% renderstyles %}`).

### `RenderQueue`

A generic queue for arbitrary HTML strings. Rendered with `{% renderqueue "name" %}`.

```python
from dj_layouts.queues import RenderQueue

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    breadcrumbs = RenderQueue()
```

`RenderQueue` templates receive `items` (list of strings) in context. Use `{{ item|safe }}` since items are raw HTML strings:

```html+django
{# myapp/breadcrumb_queue.html #}
<nav aria-label="breadcrumb">
  <ol>
    {% for item in items %}
      {{ item|safe }}
    {% endfor %}
  </ol>
</nav>
```

!!! warning "`{{ item|safe }}` is required"
    `RenderQueue` items are raw HTML strings. Without `|safe`, Django will escape them and you'll see literal `&lt;li&gt;` tags in your page. Always use `{{ item|safe }}` in `RenderQueue` templates.

## Python API

### `add_script(request, src)`

Enqueue an external script URL into the queue named `"scripts"`:

```python
from dj_layouts.queues import add_script

def my_panel(request):
    add_script(request, "/static/chart.js")
    return HttpResponse(...)
```

Raises `KeyError` if there is no queue named `"scripts"` on the active layout.

### `add_style(request, href)`

Enqueue an external stylesheet URL into the queue named `"styles"`:

```python
from dj_layouts.queues import add_style

def my_panel(request):
    add_style(request, "/static/chart.css")
    return HttpResponse(...)
```

Raises `KeyError` if there is no queue named `"styles"` on the active layout.

### `add_to_queue(request, name, item)`

Enqueue an arbitrary HTML string into a named queue:

```python
from dj_layouts.queues import add_to_queue

def my_panel(request):
    add_to_queue(request, "breadcrumbs", "<li><a href='/'>Home</a></li>")
    return HttpResponse(...)
```

`item` must be a string. Raises `KeyError` with a helpful message if `name` doesn't match any declared queue.

## Template tags

Load the `layouts` tag library first:

```html+django
{% load layouts %}
```

### `{% addscript src %}`

Enqueue an external script from a template:

```html+django
{% addscript "/static/myapp/chart.js" %}
{% addscript "https://cdn.example.com/lib.js" %}
```

Produces no output. Adds the URL to the `"scripts"` queue.

### `{% addstyle href %}`

Enqueue an external stylesheet from a template:

```html+django
{% addstyle "/static/myapp/theme.css" %}
```

Produces no output. Adds the URL to the `"styles"` queue.

### `{% enqueue "name" %} ... {% endenqueue %}`

Enqueue an arbitrary HTML block into a named queue:

```html+django
{% enqueue "breadcrumbs" %}
  <li><a href="/">Home</a></li>
  <li>Products</li>
{% endenqueue %}
```

Produces no output. The block content (`.strip()`ped) is added to the named queue.

### `{% renderscripts %}`

Render the `"scripts"` queue at the current position in the template. Typically placed at the end of `<body>` or `<head>`:

```html+django
  {% renderscripts %}
</body>
```

If the queue is empty, produces no output (no-op).

### `{% renderstyles %}`

Render the `"styles"` queue at the current position. Typically placed in `<head>`:

```html+django
  {% renderstyles %}
</head>
```

If the queue is empty, produces no output (no-op).

### `{% renderqueue "name" %}`

Render any named queue:

```html+django
{% renderqueue "breadcrumbs" %}
```

If the queue is empty, produces no output (no-op).

## Deduplication

Items are deduplicated by **exact content hash**.

- `ScriptItem` and `StyleItem` are frozen dataclasses — hashable by default
- For inline blocks (enqueued via `{% enqueue %}` or `add_to_queue()`), the content is `.strip()`ped before storing, so minor whitespace differences don't create duplicates
- Deduplication is per-request — each request starts with empty queues

If two panels enqueue `add_script(request, "/static/chart.js")`, the script appears exactly once in the rendered output.

## Ordering guarantee

**Content view items always come first, then panels in definition order.**

Even under `@async_layout` where panels run concurrently, the queue merge happens after `asyncio.gather` completes. The merge order is the definition order of panels on the Layout class, not their completion order. You get deterministic output regardless of which panel finishes first.

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()

    sidebar = Panel("myapp:sidebar")  # sidebar items come before footer items
    footer  = Panel("myapp:footer")   # ...even if footer finishes first
```

## Complete example

**Layout class:**

```python
from dj_layouts import Layout, Panel
from dj_layouts.queues import ScriptQueue, StyleQueue

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()
    styles  = StyleQueue()
    sidebar = Panel("myapp:sidebar")
```

**Panel view template (`myapp/sidebar.html`):**

```html+django
{% load layouts %}
{% addstyle "/static/myapp/sidebar.css" %}
{% addscript "/static/myapp/sidebar.js" %}

<nav class="sidebar">
  ...
</nav>
```

**Layout template (`myapp/layout.html`):**

```html+django
{% load layouts %}
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  {% renderstyles %}
</head>
<body>
  <aside>{% panel "sidebar" %}{% endpanel %}</aside>
  <main>{% panel "content" %}{% endpanel %}</main>
  {% renderscripts %}
</body>
</html>
```

The sidebar's stylesheet and script appear exactly once, even if another panel also enqueues the same files.
