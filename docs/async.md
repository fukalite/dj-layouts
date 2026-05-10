# Async Rendering

dj-layouts supports concurrent panel rendering under ASGI via `@async_layout` and `async_render_with_layout()`. This page explains how it works, what guarantees you get, and what to watch out for.

## How it works

Under `@async_layout`, all panels are rendered concurrently using `asyncio.gather`:

```
@async_layout(DefaultLayout)
async def homepage(request):
    return HttpResponse(...)

Request arrives
  │
  ├── Content view runs (your async view)
  │
  └── Panels all start concurrently:
        sidebar  ──────────────────────── done
        header   ───── done
        footer   ──────────────── done
                         ↑
                    asyncio.gather waits for all
                         │
                    Results assembled in definition order
                         │
                    Layout template rendered
                         │
                    HttpResponse returned
```

Without `@async_layout` (using plain `@layout`), panels run sequentially — each panel waits for the previous one to finish.

## Enabling async rendering

Use `@async_layout` on an **async view function**:

```python
from dj_layouts import async_layout

@async_layout("myapp.DefaultLayout")
async def homepage(request):
    data = await MyModel.objects.aget(pk=1)  # async ORM query
    return HttpResponse(f"<h1>{data.title}</h1>")
```

Or use `async_render_with_layout()` directly:

```python
from dj_layouts import async_render_with_layout

async def my_view(request):
    return await async_render_with_layout(
        request,
        "myapp.DefaultLayout",
        "myapp/page.html",
        {"title": "Hello"},
    )
```

## Sync panels auto-wrapped

You don't have to make all your panel views async. Sync panel views are automatically wrapped with `asgiref.sync_to_async`:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel("myapp:sidebar")   # sync view — auto-wrapped with sync_to_async
    header  = Panel("myapp:header")    # async view — awaited directly
```

This means you can use `@async_layout` on your content view even when some or all panel views are sync Django views. They'll still run concurrently — each in its own thread via the thread pool executor.

!!! note "ORM queries in sync panels"
    Sync panel views that use the Django ORM work fine — `sync_to_async` runs them in a thread pool where synchronous database access is allowed. Just write normal sync ORM calls in your panel views.

## Ordering guarantees

**Results are always assembled in panel definition order, regardless of completion order.**

Even if `footer` finishes before `sidebar`, the final rendered output will have panels assembled in the order they are defined on the Layout class. This is because `asyncio.gather(*tasks, return_exceptions=True)` preserves result order.

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel("myapp:sidebar")   # output position: 1st
    header  = Panel("myapp:header")    # output position: 2nd
    footer  = Panel("myapp:footer")    # output position: 3rd
```

The layout template always sees `sidebar`, `header`, `footer` with their respective HTML — not swapped because one panel ran faster.

## Render queue ordering under async

Render queues also respect this ordering guarantee:

1. Content view's queued items come first
2. Panel items follow in panel **definition order** (not completion order)

```python
# sidebar enqueues sidebar.js
# footer enqueues footer.js
# Even if footer finishes first, output order is: sidebar.js then footer.js
```

See [Render Queues](render-queues.md) for the queue API.

## Error isolation

Under `@async_layout`, one panel failing does not prevent other panels from completing. This is because `asyncio.gather` is called with `return_exceptions=True`:

```python
results = await asyncio.gather(*tasks, return_exceptions=True)
```

If a panel raises an exception, it appears as an `Exception` instance in the results list. The layout engine then calls `on_panel_error()` for that panel and continues assembling the rest. The page still renders — just with an error fallback in the failed panel's slot.

See [Error Handling](error-handling.md) for how to customise error behaviour.

## ASGI requirement

Concurrent panel rendering requires running Django under ASGI (e.g. Uvicorn, Daphne, Hypercorn). Under WSGI, `asyncio.gather` still works but the concurrency benefit is limited — the event loop runs in a single thread.

For maximum throughput, use an ASGI server with async views and async-capable panel views (or rely on auto-wrapping for sync panels).

## Comparison: `@layout` vs `@async_layout`

| | `@layout` | `@async_layout` |
|---|---|---|
| View must be async | No | Yes |
| Panels run | Sequentially | Concurrently |
| Sync panels | Called directly | Wrapped with `sync_to_async` |
| ASGI required | No | No (but benefits require ASGI) |
| Error isolation | Per-panel try/except | `return_exceptions=True` |

## Example: parallel panel rendering

```python
# myapp/layouts.py
from dj_layouts import Layout, Panel

class DashboardLayout(Layout):
    template = "myapp/dashboard.html"

    summary   = Panel("myapp:summary_panel")    # hits the database
    activity  = Panel("myapp:activity_panel")   # hits the database
    alerts    = Panel("myapp:alerts_panel")     # hits an external API

# myapp/views.py
from dj_layouts import async_layout
from django.http import HttpResponse

@async_layout("myapp.DashboardLayout")
async def dashboard(request):
    request.layout_context["page_title"] = "Dashboard"
    return HttpResponse("<h2>Welcome back!</h2>")
```

With `@async_layout`, `summary`, `activity`, and `alerts` all start at the same time. If each takes 50ms, the total panel rendering time is ~50ms instead of ~150ms.
