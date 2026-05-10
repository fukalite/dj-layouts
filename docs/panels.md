# Panels

Reference for `Panel` — the configuration object that declares how a named region in a `Layout` is populated.

## What is a Panel?

A `Panel` is a class attribute on a `Layout`. It describes the *source* of the HTML for that region. The Layout engine resolves the source at request time and makes the result available in the layout template via `{% panel "name" %}`.

```python
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel("myapp:sidebar")   # sidebar region → calls the "myapp:sidebar" view
    footer  = Panel("myapp:footer")    # footer region  → calls the "myapp:footer" view
```

## Source types

`Panel` accepts exactly one source specification: either a positional argument or one of the `url_name=` / `literal=` keyword arguments.

### URL name (namespaced)

Any string containing `:` is treated as a namespaced URL name and reversed via `django.urls.reverse()`.

```python
Panel("myapp:sidebar")       # → reverse("myapp:sidebar") → call that view
Panel("myapp:item_detail")   # → reverse("myapp:item_detail") → call that view
```

`NoReverseMatch` propagates — there is no silent fallback. If the URL name doesn't exist you get an error at request time.

### URL name (non-namespaced) — `url_name=` kwarg

Non-namespaced URL names don't contain `:`, so the auto-detection heuristic would treat them as literals. Use the `url_name=` keyword argument to force URL reversal:

```python
Panel(url_name="home")       # → reverse("home") → call that view
Panel(url_name="about")      # → reverse("about") → call that view
```

`url_name=` always calls `reverse()`, regardless of whether `:` is present.

### Literal HTML — positional string without `:`

A string with no `:` is returned as-is without any URL resolution:

```python
Panel("<p>Static content</p>")   # returned verbatim
Panel("")                         # empty string — template fallback is used
```

### Literal HTML — `literal=` kwarg

Use `literal=` to force literal treatment even when the string contains `:`:

```python
Panel(literal="See: https://example.com for more")  # never reversed
Panel(literal="<a href='http://x.com'>Link</a>")    # returned verbatim
```

### Callable

Pass any callable that accepts `(request, **context)` and returns an `HttpResponse` or `str`:

```python
def my_panel_fn(request, **kwargs):
    return f"<p>Hello {request.user}</p>"

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    greeting = Panel(my_panel_fn)
```

The callable receives the cloned panel request plus any `context` kwargs from the `Panel` definition.

### List of sources

Pass a list to combine multiple sources into one panel. Each item in the list is resolved independently and results are joined with the `join` separator:

```python
Panel(["myapp:widget_a", "myapp:widget_b"], join="\n")
Panel(["myapp:widget_a", "<hr>", "myapp:widget_b"])  # mixed URL + literal
```

### `None` — empty panel

`Panel(None)` (or just `Panel()`) produces empty output. The layout template's fallback content is rendered instead:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    ads = Panel(None)   # always empty — no ad panel rendered
```

In the template:

```html+django
{% panel "ads" %}<p>No ads configured.</p>{% endpanel %}
```

## All source type behaviours at a glance

| Source | Contains `:` | How it resolves |
|---|---|---|
| `Panel("app:name")` | Yes | `reverse("app:name")` → call view |
| `Panel("plain string")` | No | Return as literal HTML |
| `Panel(url_name="home")` | N/A | Always `reverse("home")` → call view |
| `Panel(literal="x:y")` | Yes | Return as literal HTML (never reversed) |
| `Panel(callable)` | N/A | Call `callable(request, **context)` |
| `Panel([...])` | N/A | Resolve each item, join results |
| `Panel(None)` or `Panel()` | N/A | Empty — template fallback renders |

## Keyword arguments

### `context=`

Extra keyword arguments forwarded to the panel's source view or callable.

```python
Panel("myapp:item_detail", context={"pk": 42})
```

**Important:** Panel context kwargs are merged **on top of** URL-captured route parameters. Panel context wins:

```python
# URL: /items/<pk>/
# Panel: Panel("myapp:item_detail", context={"pk": 99})
# The view receives pk=99, not whatever the layout URL captured
```

This is intentional — it lets you pin a panel to a specific object without creating a dedicated URL.

!!! warning "Never put untrusted values in `Panel.context`"
    `Panel.context` is **configuration-time data** — it's fixed when your `layouts.py` module loads. Do not use it to pass user-supplied or request-time data. For request-time data, use `get_layout_context()` or have the panel view fetch it from the database itself.

    Putting `request.GET["user_id"]` in a `Panel.context` is not possible (there's no request at class-definition time) and is not the intended pattern. The panel view should read `request.GET` directly.

### `join=`

**Type:** `str` | **Default:** `""`

Separator string used when `source` is a list. Items are joined with this string after resolution:

```python
Panel(["myapp:widget_a", "myapp:widget_b"], join="<hr>")
```

Ignored when `source` is not a list.

### `url_name=`

Force URL name resolution. See [URL name (non-namespaced)](#url-name-non-namespaced-url_name-kwarg) above.

### `literal=`

Force literal string treatment. See [Literal HTML — literal= kwarg](#literal-html-literal-kwarg) above.

## Panel priority order

When a request is processed, the effective panel for each name is determined in this order (last wins):

1. **Class-level definition** — `Panel(...)` as a class attribute on the Layout
2. **Per-view override** — `panels={"name": Panel(...)}` passed to `@layout` or `render_with_layout()`
3. **Template fallback** — the content between `{% panel "name" %}` and `{% endpanel %}`

The template fallback is not really an "override" — it only applies when the resolved panel produces empty output (empty string).

### Per-view panel overrides

You can override individual panels per view without subclassing:

```python
@layout("myapp.DefaultLayout", panels={"sidebar": Panel("myapp:user_sidebar")})
def profile_page(request):
    return HttpResponse(...)
```

To suppress a panel for a specific view, pass `None`:

```python
@layout("myapp.DefaultLayout", panels={"sidebar": None})
def landing_page(request):
    return HttpResponse(...)  # no sidebar on this page
```

## Panel resolution: sync vs async

Under `@layout`, panels are resolved **sequentially** (one after another).

Under `@async_layout`, all panels are resolved **concurrently** via `asyncio.gather`. Sync views are automatically wrapped with `sync_to_async`. See [Async](async.md) for details.

## Panel requests

Panels always receive a **cloned** version of the original request:

- `method` is always `GET`
- `POST` and `FILES` are cleared
- `request.user`, `request.session`, `request.cookies`, `request.resolver_match` are preserved
- `request.layout_role` is set to `"panel"`
- `request.is_layout_partial` is `False`
- `request.layout_context` is a `FrozenLayoutContext` (read-only copy)

Panel views do **not** go through middleware again. Auth and session data are available (from the original request), but middleware side effects (e.g. security headers, cookie updates) do not fire.

See [Security](security.md) for implications of this.
