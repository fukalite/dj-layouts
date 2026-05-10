# Decorators

Reference for `@layout`, `@panel_only`, `@async_layout`, and the `render_with_layout()` function.

## `@layout`

```python
from dj_layouts import layout

@layout(layout_class, *, panels=None)
def my_view(request):
    ...
```

Wraps a **sync** view to render inside a Layout. When the decorated view is called:

1. `request.layout_role` is set to `"main"`
2. `request.is_layout_partial` is set to `False`
3. Layout context is built and set on `request.layout_context` (before your view runs)
4. Your view is called and returns a response
5. Non-200 / streaming responses are returned as-is (no layout wrapping)
6. The response content is extracted and passed to the layout engine as the `"content"` panel
7. All other panels are resolved (sequentially)
8. The layout template is rendered with all panel outputs
9. A full-page `HttpResponse` is returned

### Parameters

**`layout_class`** — `type[Layout] | str`

The Layout class or a dotted string reference:

```python
@layout(DefaultLayout)             # direct class reference
@layout("myapp.DefaultLayout")     # dotted string — resolved lazily, avoids circular imports
```

**`panels`** — `dict[str, Panel | None] | None`

Per-view panel overrides. Keys are panel names; values are `Panel` instances or `None` to suppress:

```python
@layout(DefaultLayout, panels={"sidebar": Panel("myapp:user_sidebar")})
def profile(request):
    ...

@layout(DefaultLayout, panels={"sidebar": None})
def landing(request):
    ...  # no sidebar on this page
```

Per-view overrides take precedence over class-level panel definitions.

### Non-200 and streaming passthrough

If your view returns a non-200 response (redirect, error page), the layout is **skipped** and the response is returned unchanged:

```python
@layout(DefaultLayout)
def my_view(request):
    if not request.user.is_authenticated:
        return redirect("/login/")   # 302 — passed through, no layout
    return HttpResponse("...")       # 200 — wrapped in layout
```

`StreamingHttpResponse` is always passed through unchanged — streaming responses cannot be wrapped in a layout.

### `TemplateResponse` eager rendering

If your view returns a `TemplateResponse` (e.g. from `render()`), it is **force-rendered immediately** before the layout engine processes it:

```python
@layout(DefaultLayout)
def my_view(request):
    return render(request, "myapp/page.html", {"x": 1})
    # TemplateResponse is force-rendered → its content is extracted
```

!!! warning "Middleware that modifies TemplateResponse will not affect panel content"
    Any middleware that normally modifies the `TemplateResponse` context or template *after* the view returns will not run — the response is already rendered. This is an inherent trade-off of the layout model. If your middleware needs to inject template variables, use `get_layout_context()` or `layout_context_defaults` instead.

### No-op when already in panel role

`@layout` is a no-op when `request.layout_role == "panel"`. This means you can safely decorate a view that can be called both as a main content view and as a panel:

```python
@layout("myapp.DefaultLayout")   # no-op when called as a panel
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    return render(request, "myapp/article_detail.html", {"article": article})
```

When called directly, it renders the full layout. When called as a panel from another layout, `@layout` detects `layout_role == "panel"` and skips the layout wrapping, returning just the partial.

### Accessing layout context in the view

`request.layout_context` is set **before** your view is called, so you can read it immediately and write to it to pass page-level data to the layout template:

```python
@layout(DefaultLayout)
def my_view(request):
    request.layout_context["page_title"] = "Home"
    return HttpResponse(...)
```

See [Layout Context](layout-context.md) for the full details.

---

## `@panel_only`

```python
from dj_layouts import panel_only

@panel_only
def my_panel(request):
    ...
```

Marks a view as panel-only. Returns **403 Forbidden** if called directly (i.e. `request.layout_role != "panel"`). No arguments.

### When 403 is returned

- Called directly via the browser with no `layout_role` set → 403
- Called with `request.layout_role == "main"` → 403
- Called with `request.layout_role == "panel"` → view runs normally

### Mutual exclusivity with `@layout`

Combining `@panel_only` with `@layout` raises `TypeError` at decoration time:

```python
@layout(DefaultLayout)
@panel_only        # ← TypeError: Cannot apply @layout to a @panel_only view
def bad_view(request):
    ...
```

The check runs when the decorators are applied (module import time), not at request time.

### Protecting panel URLs

`@panel_only` is the standard way to prevent panels from being accessed directly. This is important for views that produce incomplete HTML fragments (no `<html>` wrapper, no `<head>`, etc.):

```python
@panel_only
def sidebar(request):
    # This view returns a <nav> fragment — calling it directly makes no sense
    return render(request, "myapp/sidebar.html", {})
```

See [Security](security.md) for additional considerations around panel access.

---

## `@async_layout`

```python
from dj_layouts import async_layout

@async_layout(layout_class, *, panels=None)
async def my_view(request):
    ...
```

Async version of `@layout`. Requires an **async view function**. Panels run **concurrently** via `asyncio.gather`.

```python
@async_layout("myapp.DefaultLayout")
async def homepage(request):
    return HttpResponse("<h1>Welcome!</h1>")
```

### Requires an async view

Passing a sync view to `@async_layout` raises `TypeError` at decoration time:

```python
@async_layout(DefaultLayout)
def bad_view(request):   # TypeError: @async_layout requires an async view
    ...
```

Use `@layout` for sync views.

### Concurrent panel rendering

All panels run concurrently. A slow panel doesn't block the others. Results are assembled in **definition order** regardless of completion order — see [Async](async.md) for full details.

### Sync panels auto-wrapped

Panel views don't have to be async. Sync panel views are automatically wrapped with `sync_to_async`. This means you can mix async and sync panel views freely:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel("myapp:sidebar")  # sync view — auto-wrapped
    header  = Panel("myapp:header")   # async view — called directly
```

### Same passthrough rules as `@layout`

Non-200 responses and `StreamingHttpResponse` are passed through unchanged. `TemplateResponse` is force-rendered. The no-op-when-panel-role behaviour is the same.

---

## `render_with_layout()`

```python
from dj_layouts import render_with_layout

def my_view(request):
    return render_with_layout(
        request,
        "myapp.DefaultLayout",    # or the class directly
        "myapp/page.html",
        {"article": article},
        panels={"sidebar": Panel(...)},  # optional overrides
    )
```

An explicit alternative to the `@layout` decorator. Renders `template_name` as the content panel, assembles all other panels, and returns a full-page `HttpResponse`.

### Signature

```python
render_with_layout(
    request,
    layout_class,   # type[Layout] | str
    template_name,  # str
    context=None,   # dict | None
    *,
    panels=None,    # dict[str, Panel | None] | None
) -> HttpResponse
```

### When to use it

Use `render_with_layout()` when you want explicit control and don't want the decorator's automatic behaviour:

- Class-based views (where `@layout` can't be applied to `dispatch` easily)
- Conditional layout rendering (sometimes layout, sometimes not)
- Integration with third-party decorator stacks

### `async_render_with_layout()`

The async equivalent:

```python
from dj_layouts import async_render_with_layout

async def my_async_view(request):
    return await async_render_with_layout(
        request,
        "myapp.DefaultLayout",
        "myapp/page.html",
        {"data": await fetch_data()},
    )
```

Panels run concurrently via `asyncio.gather`, same as `@async_layout`.
