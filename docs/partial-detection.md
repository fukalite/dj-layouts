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

---

## Out-Of-The-Box SPA Routing (Smart Routing)

By simply setting `HTMX_SMART_ROUTING = True` and adding `hx-boost="true"` to your `<body>`, `dj-layouts` magically transforms standard Django applications into buttery-smooth Single Page Applications (SPAs).

It intelligently manages layout transitions, returning partials when layouts match (fast) and swapping the `<body>` when traversing layouts, maintaining full SEO compatibility and zero JavaScript routing overhead.

### How it works under the hood
1. **Layout Tracker Cookie:** When a full layout is first loaded, `dj-layouts` sets a tracking cookie (`dj_layout_current`) identifying which layout class rendered the page.
2. **Dynamic Retargeting:** On subsequent boosted links/requests:
   - If the next view uses the **same layout**, `dj-layouts` returns only the partial view response and adds the `HX-Retarget` header specifying your main content panel selector (default: `#panel-content`). HTMX swaps only the content panel without page flashes.
   - If the next view uses a **different layout**, `dj-layouts` assembles the entire layout, sets `HX-Retarget: body` and `HX-Reswap: outerHTML` to tell HTMX to cleanly replace the whole body, and updates the tracking cookie.

### Caveats & Watchouts (CRITICAL)

#### 1. Error Handling (500 / 404)
You **MUST** route your Django error handlers (`handler404`, `handler500`) to custom views that are decorated with `@layout`. If you do not, and an HTMX request triggers an error, Django will return an un-decorated full HTML error page. HTMX will inject this raw HTML into your `#panel-content` target, breaking the UI. When decorated, `dj-layouts` safely renders the error page *inside* the current layout's main panel.

#### 2. Cross-Subdomain AJAX
HTMX `hx-boost` strictly ignores cross-origin links (including subdomains). If your application spans multiple subdomains (e.g., `news.app.com` and `circles.app.com`), you must:
- Set `HTMX_COOKIE_DOMAIN = ".app.com"` so the layout cookie is shared across subdomains.
- Use a custom JS snippet to manually trigger `htmx.ajax` on cross-subdomain links, bypassing the strict origin check.

#### 3. The Escape Hatch
If a view logic updates data that affects a parent panel (e.g., updating a username that appears in the sidebar), the view can set `request.dj_layouts_force_full = True`. This forces `dj-layouts` to skip partial rendering and return the full layout, allowing HTMX to gracefully refresh the entire page state seamlessly.

#### 4. Independent Subpanels
Forms or buttons that should *only* update a specific subpanel must explicitly define their target (e.g., `hx-target="#panel-sidebar"`). This overrides the smart router's default content targeting.

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
| `DJ_LAYOUTS["HTMX_SMART_ROUTING"]` | `False` | Enable intelligent SPA transitions and cookie layout tracking |
| `DJ_LAYOUTS["HTMX_CONTENT_TARGET"]` | `"#panel-content"` | CSS selector target for same-layout partial rendering |
| `DJ_LAYOUTS["HTMX_COOKIE_NAME"]` | `"dj_layout_current"` | Cookie name used to track the current layout |
| `DJ_LAYOUTS["HTMX_COOKIE_DOMAIN"]` | `None` | Domain scope for the layout tracking cookie |

See [Settings](settings.md) for the full settings reference.
