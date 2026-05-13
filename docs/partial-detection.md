# Partial Detection

Partial detection lets the `@layout` decorator and `LayoutMixin` skip layout assembly and return the view's raw response — when a request signals that it only wants the partial HTML (for example, an HTMX request or an explicit query parameter).

## How it works

Before the view runs, dj-layouts calls each configured **detector** in order. If any detector returns `True` the request is marked as partial: `request.is_layout_partial = True` and the view's response is returned directly without layout wrapping. If no detector fires the full layout is assembled as normal.

`render_with_layout()` **always** assembles the full layout — detection does not run there. Use `@layout` or `LayoutMixin` when you need detection.

## Configuration

Set `PARTIAL_DETECTORS` in your `DJ_LAYOUTS` settings dict to a list of dotted import paths:

```python
# settings.py
DJ_LAYOUTS = {
    "PARTIAL_DETECTORS": [
        "dj_layouts.detection.htmx_detector",
        "dj_layouts.detection.query_param_detector",
    ],
}
```

Detectors are loaded lazily on first request. An invalid dotted path raises `ImproperlyConfigured`.

**Default:** `[]` — no detectors, layout always assembled.

## Built-in detectors

### `dj_layouts.detection.never_detector`

Always returns `False`. Layout is always assembled. This is effectively the same as not listing any detector, and can be used as a placeholder.

### `dj_layouts.detection.htmx_detector`

Returns `True` when the request has the `HX-Request: true` header, which HTMX sets on every request it makes.

```python
DJ_LAYOUTS = {"PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"]}
```

With this configured, HTMX fetch requests receive only the partial HTML — perfect for fragment updates. Full page navigations (which lack the header) receive the complete layout.

### `dj_layouts.detection.query_param_detector`

Returns `True` when `?_partial=1` is in the query string. Useful for testing or JavaScript fetch calls where you control the URL.

```python
DJ_LAYOUTS = {"PARTIAL_DETECTORS": ["dj_layouts.detection.query_param_detector"]}
```

## Custom detectors

A detector is any callable matching this signature:

```python
def my_detector(request: HttpRequest) -> bool:
    ...
```

Return `True` to trigger partial mode, `False` to let layout assembly proceed. Register it by dotted path:

```python
# myapp/detectors.py
def json_request_detector(request):
    return request.headers.get("Accept") == "application/json"

# settings.py
DJ_LAYOUTS = {"PARTIAL_DETECTORS": ["myapp.detectors.json_request_detector"]}
```

## Detector ordering

Detectors are called in list order. The first `True` result wins — subsequent detectors are not called.

## Detector exceptions

By default, if a detector raises an exception it is logged at `WARNING` level and treated as `False` (the layout is still assembled — the exception does not surface to the user).

To re-raise detector exceptions instead, set:

```python
DJ_LAYOUTS = {"DETECTOR_RAISE_EXCEPTIONS": True}
```

This is useful in development if you want to catch broken detectors immediately.

## Request attributes

When detection runs, these attributes are set on the request **before** the view executes:

| Attribute | Value |
|---|---|
| `request.layout_role` | `"main"` |
| `request.is_layout_partial` | `True` (partial) or `False` (full) |
| `request.layout_context` | `LayoutContext` instance (read-only copy in panel requests) |
| `request.layout_queues` | Fresh queue dict (even in partial mode — view can enqueue) |

See [Request Attributes](request-attributes.md) for the full reference.

---

## `LayoutMixin`

`LayoutMixin` brings the same layout integration to Django class-based views.

```python
from django.views.generic import TemplateView
from dj_layouts import LayoutMixin

from myapp.layouts import DefaultLayout


class DashboardView(LayoutMixin, TemplateView):
    layout_class = DefaultLayout
    template_name = "dashboard/partial.html"
```

### Attributes

| Attribute | Type | Default | Description |
|---|---|---|---|
| `layout_class` | `type[Layout]` or `str` | Required | The Layout class to wrap responses in. Accepts a dotted string (resolved via the layout registry). |
| `layout_panels` | `dict[str, Panel \| None]` | `None` | Per-view panel overrides, equivalent to the `panels=` kwarg on `@layout`. |

### Sync and async handler methods

`LayoutMixin.dispatch` is `async`. This means Django treats the view as async, and `as_view()` returns an async callable. Both sync and async handler methods (`get`, `post`, etc.) work:

- **Sync handlers** — called and awaited transparently; no change needed
- **Async handlers** — called and awaited as coroutines

On WSGI, Django's `async_to_sync` adapter handles async views transparently. You do not need ASGI to use `LayoutMixin`.

### Partial detection

Partial detection runs in `dispatch` the same way it does in `@layout`. An HTMX request against a `LayoutMixin` CBV returns the partial HTML directly, without layout wrapping.

### `TemplateResponse` force-rendering

`TemplateView` and similar generic views return a `TemplateResponse`, which is not rendered until accessed. `LayoutMixin` force-renders the response before passing the HTML to the layout engine — and also before returning in partial mode.

### Dotted string `layout_class`

The layout registry key format is `<app_label>.<ClassName>`, where `app_label` is the first segment of the module where the Layout class is defined:

```python
class DashboardView(LayoutMixin, TemplateView):
    layout_class = "myapp.DefaultLayout"   # myapp/layouts.py → DefaultLayout
    template_name = "dashboard/partial.html"
```

### Non-200 and streaming responses

As with `@layout`, non-200 responses (redirects, error pages) and `StreamingHttpResponse` are returned directly without layout wrapping.

### Missing `layout_class`

If `layout_class` is not set, `dispatch` raises `ImproperlyConfigured` immediately.

### When used as a panel

If a `LayoutMixin` CBV is called as a panel (i.e. `request.layout_role == "panel"`), the mixin passes through to the CBV's normal dispatch without layout assembly. This is consistent with how `@layout` behaves in panel role.

---

## Settings reference

| Setting | Default | Description |
|---|---|---|
| `DJ_LAYOUTS["PARTIAL_DETECTORS"]` | `[]` | List of dotted detector paths |
| `DJ_LAYOUTS["DETECTOR_RAISE_EXCEPTIONS"]` | `False` | Re-raise detector exceptions instead of logging |

See [Settings](settings.md) for the full settings reference.
