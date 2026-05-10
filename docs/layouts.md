# Layouts

Reference for the `Layout` class — the central configuration object that assembles a full page from panels.

## Declaring a Layout

Subclass `dj_layouts.Layout` and set `template`:

```python
# myapp/layouts.py
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "myapp/layout.html"
```

`template` is required. Omitting it raises `TypeError` at class definition time.

## Class attributes

### `template`

**Type:** `str` | **Required**

Path to the layout template, relative to Django's template directories.

```python
template = "myapp/layout.html"
```

Override `get_template()` if you need to select the template dynamically.

### `error_template`

**Type:** `str` | **Default:** `"layouts/error.html"`

Template rendered by `on_panel_error()` when a panel fails in production mode (non-debug). dj-layouts ships with a default `layouts/error.html` that shows a collapsible error box. Override on your Layout class to use a custom template:

```python
error_template = "myapp/panel_error.html"
```

The template receives a single context variable `error` — a `PanelError` instance with `panel_name`, `source`, `exception`, and `traceback_str` attributes.

See [Error Handling](error-handling.md) for full details.

### `layout_context_defaults`

**Type:** `dict[str, Any]` | **Default:** `{}`

Static key/value pairs available in the layout template and in the content view via `request.layout_context`. These are the lowest-priority defaults; they are overridden by `get_layout_context()` and then by the content view's own writes to `request.layout_context`.

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {
        "site_name": "My Site",
        "theme": "light",
    }
```

### Panel class attributes

`Panel(...)` instances assigned as class attributes become the layout's named panels:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"

    sidebar = Panel("myapp:sidebar")
    footer  = Panel("myapp:footer")
    banner  = Panel(None)  # empty by default, template fallback is used
```

Attribute name = panel name used in `{% panel "name" %}` in the template.

Panels are inherited by subclasses; a subclass's own panel definitions take precedence over parent class panels of the same name.

### `ScriptQueue` / `StyleQueue` / `RenderQueue`

Render queue instances declared as class attributes on the Layout. See [Render Queues](render-queues.md) for setup and usage.

```python
from dj_layouts import Layout
from dj_layouts.queues import ScriptQueue, StyleQueue

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()
    styles  = StyleQueue()
```

!!! warning "Queues must be explicitly declared"
    Queues do not appear automatically. You must declare them as class attributes to use them. The attribute name becomes the queue name used in template tags like `{% renderqueue "scripts" %}`.

## Overridable methods

### `get_layout_context(request)`

Return a dict of extra context variables. Called after `layout_context_defaults` is applied. The content view can still override individual keys by writing to `request.layout_context` afterwards.

```python
def get_layout_context(self, request):
    return {
        "current_user": request.user,
        "page_title": "My Site",
    }
```

**Return type:** `dict[str, Any]`

### `get_template(request)`

Return the template path to render. Override this when the template varies per-request (e.g. different templates for different device types):

```python
def get_template(self, request):
    if request.META.get("HTTP_HX_REQUEST"):
        return "myapp/layout_partial.html"
    return self.template
```

**Return type:** `str`

### `on_panel_error(request, error)`

Called in production (non-debug) mode when a panel raises an exception. Return an HTML string to use as the panel's output (typically an error message or empty string).

```python
def on_panel_error(self, request, error):
    # error.panel_name, error.source, error.exception, error.traceback_str
    logger.error("Panel %s failed", error.panel_name, exc_info=error.exception)
    return ""  # silently suppress the panel
```

The default implementation logs the error and renders `self.error_template`.

In **debug mode** (`DJ_LAYOUTS["DEBUG_ERRORS"] = True` or `DEBUG = True`), this method is bypassed entirely — a `PanelRenderError` is raised so Django's debug error page appears. See [Error Handling](error-handling.md).

**Parameters:**

- `request` — the original (main view) request
- `error` — a `PanelError` dataclass

**Return type:** `str`

## Registration and autodiscovery

### Automatic registration

Subclassing `Layout` registers the class automatically. You do not call a register function yourself.

**Registration key:** `"<app_label>.<ClassName>"`

The `app_label` is the first segment of the module's dotted path. For `myapp.layouts.DefaultLayout`, the key is `"myapp.DefaultLayout"`.

```python
# myapp/layouts.py
class DefaultLayout(Layout):   # registered as "myapp.DefaultLayout"
    template = "myapp/layout.html"
```

### Autodiscovery

dj-layouts uses Django's `autodiscover_modules("layouts")` — the same mechanism used by `django.contrib.admin`. On startup it imports every `layouts.py` in your installed apps, which triggers subclass registration.

**You must place Layout classes in `layouts.py`** (or import them there) for autodiscovery to work. A Layout defined in `views.py` or `models.py` will not be registered until that module is imported.

### Listing registered layouts

```python
from dj_layouts.base import _registry
print(list(_registry.keys()))
# ['myapp.DefaultLayout', 'otherapp.BlogLayout', ...]
```

### Resolving by dotted string

```python
from dj_layouts import Layout

layout_cls = Layout.resolve("myapp.DefaultLayout")
```

Raises `KeyError` with a helpful message listing available layouts if the key is not found.

## Inheritance

Layout classes can inherit from each other. Panel definitions are inherited; a subclass can override individual panels:

```python
class BaseLayout(Layout):
    template = "myapp/base.html"
    sidebar = Panel("myapp:sidebar")
    footer  = Panel("myapp:footer")

class BlogLayout(BaseLayout):
    template = "myapp/blog.html"
    # Inherits footer from BaseLayout, overrides sidebar
    sidebar = Panel("blog:sidebar")
```

`BlogLayout._panels` will be `{"sidebar": Panel("blog:sidebar"), "footer": Panel("myapp:footer")}`.

## Dotted string references

Passing a Layout class directly to `@layout` creates an import-time dependency between `views.py` and `layouts.py`. Use a dotted string to avoid circular imports:

```python
# views.py
from dj_layouts import layout

@layout("myapp.DefaultLayout")   # resolved lazily from the registry
def homepage(request):
    ...
```

The string is resolved when the first request hits the view, by which time autodiscovery has run and the class is registered.

!!! warning "String refs require autodiscovery to have run"
    Dotted string refs fail with `KeyError` if the Layout class has not been imported yet. This is normally fine — startup autodiscovery handles it. If you're using `Layout.resolve()` in tests or management commands, make sure `AppConfig.ready()` has run (or import the layouts module manually).
