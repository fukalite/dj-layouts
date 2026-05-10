# Request Attributes

dj-layouts adds several attributes to the Django request object during layout processing. This page documents each attribute: what it is, when it's set, and how to use it.

## Overview

| Attribute | Type | Set by | Available in |
|---|---|---|---|
| `request.layout_role` | `str \| None` | `@layout` / `@async_layout` / clone | All views during layout processing |
| `request.is_layout_partial` | `bool` | `@layout` / `@async_layout` / clone | All views during layout processing |
| `request.layout_context` | `LayoutContext` or `FrozenLayoutContext` | Layout engine | Content view (read/write), panel views (read-only) |
| `request.layout_queues` | `dict[str, Queue]` | Layout engine | Content view and panel views |

None of these attributes exist on requests outside of layout processing (e.g. views not decorated with `@layout`). Use `getattr(request, "layout_role", None)` for safe access.

---

## `request.layout_role`

**Type:** `str | None` (not set on non-layout requests)

**Values:**

- `"main"` — this request is the main content view (set by `@layout` / `@async_layout`)
- `"panel"` — this request is a cloned panel request (set by the layout engine on the clone)

**When it's set:**

- Set to `"main"` **before** your content view is called by `@layout` / `@async_layout`
- Set to `"panel"` on the cloned request before a panel view is called
- Not set on requests that don't go through layout processing

**How to use it:**

Check `layout_role` to make a view behave differently depending on whether it's the main content or a panel:

```python
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    if getattr(request, "layout_role", None) == "panel":
        # Called as a panel — return a compact card
        return render(request, "myapp/article_card.html", {"article": article})
    # Called directly — return the full article
    return render(request, "myapp/article_detail.html", {"article": article})
```

`@layout` uses `layout_role` internally to implement its no-op behaviour when a decorated view is called as a panel.

---

## `request.is_layout_partial`

**Type:** `bool` (not set on non-layout requests)

**Values:**

- `False` — always set to `False` by the current implementation

**When it's set:**

Set to `False` on the main request by `@layout` / `@async_layout`, and set to `False` on cloned panel requests.

!!! note "Partial detection is planned"
    `is_layout_partial` is reserved for a future partial detection feature (e.g. detecting HTMX requests or a `?partial=1` query parameter and returning just the content panel without the full layout). The attribute exists now so views can check it for forward compatibility. It is always `False` in the current implementation.

**Safe access:**

```python
if getattr(request, "is_layout_partial", False):
    # Partial mode — skip the layout
    ...
```

---

## `request.layout_context`

**Type:** `LayoutContext` (in content view) or `FrozenLayoutContext` (in panel views)

**When it's set:**

Set on the main request **before** the content view is called. Set as a frozen copy on each cloned panel request.

**In the content view — full read/write:**

```python
@layout("myapp.DefaultLayout")
def my_view(request):
    # Read
    site = request.layout_context["site_name"]
    theme = request.layout_context.get("theme", "light")

    # Write
    request.layout_context["page_title"] = "My Page"
    request.layout_context.update({"active_nav": "home"})

    return HttpResponse(...)
```

**In panel views — read-only:**

```python
@panel_only
def sidebar(request):
    # Read works fine
    active = request.layout_context.get("active_nav", "home")

    # Write raises TypeError
    request.layout_context["key"] = "val"  # TypeError!

    return render(request, "myapp/sidebar.html", {"active": active})
```

Writing to `request.layout_context` in a panel view raises `TypeError: layout_context is read-only in panel views`.

**See also:** [Layout Context](layout-context.md) for the full merge order, three-stage build process, and template usage.

---

## `request.layout_queues`

**Type:** `dict[str, Queue]`

A dictionary mapping queue names to fresh queue instances for the current request. Keys match the queue attribute names declared on the Layout class.

**When it's set:**

Set on the main request before the content view is called. Fresh empty queue instances are created for each request — the Layout's class-level queue objects are config objects (factories), not shared state.

A fresh set of queues is also created on each cloned panel request — panel views enqueue into their own request's queues, and the layout engine merges them after all panels complete.

**How to use it directly:**

You rarely need to access `request.layout_queues` directly. Use the helper functions instead:

```python
from dj_layouts.queues import add_script, add_style, add_to_queue

add_script(request, "/static/myapp/chart.js")   # queues into request.layout_queues["scripts"]
add_style(request, "/static/myapp/theme.css")   # queues into request.layout_queues["styles"]
add_to_queue(request, "breadcrumbs", "<li>...</li>")  # queues into request.layout_queues["breadcrumbs"]
```

**Direct access (advanced):**

```python
@panel_only
def my_panel(request):
    queue = request.layout_queues.get("scripts")
    if queue is not None:
        # Low-level access — normally use add_script() instead
        queue.add("/static/myapp/script.js")
    return HttpResponse(...)
```

Accessing a queue name that doesn't exist raises `KeyError` with a helpful message listing available queues.

**See also:** [Render Queues](render-queues.md) for the full queue API and template tags.

---

## Safe access pattern

All layout attributes may be absent on requests that don't go through layout processing (e.g. views not decorated with `@layout`, middleware, signal handlers). Use `getattr` with a default:

```python
role = getattr(request, "layout_role", None)
context = getattr(request, "layout_context", {})
is_partial = getattr(request, "is_layout_partial", False)
queues = getattr(request, "layout_queues", {})
```
