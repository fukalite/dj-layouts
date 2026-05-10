# Phase 5 — Partial Detection + LayoutMixin

> **Prerequisites:** Phase 1 complete. (Phases 3 and 4 are independent.) Read [`docs/layouts-plan.md`](../layouts-plan.md) §"Partial Detection" and §"Class-Based Views — LayoutMixin". Read [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Clarify the exact detection strategy ordering, what happens when a detector raises an exception, and whether `LayoutMixin` should support `async_dispatch`. Do not write production code until you have a failing test.

## Goal

Two additions that are independent of each other but logically grouped:

1. **Partial detection** — the `@layout` decorator can detect that the current request wants only the partial (e.g. HTMX request), and skip layout assembly entirely.
2. **`LayoutMixin`** — CBVs get the same layout integration as FBVs via `@layout`, using a `layout_class` attribute.

## Scope

### Files to create/modify

```
src/layouts/
    detection.py          # New: detector protocol, built-in detectors, engine
    mixins.py             # New: LayoutMixin
    decorators.py         # Modified: wire detection into @layout
    rendering.py          # Modified: skip layout if detection fires
    __init__.py           # Modified: export LayoutMixin, detection utilities
    tests/
        test_detection.py # New
        test_mixins.py    # New
```

### Public API additions

```python
from layouts import LayoutMixin
```

Detectors are referenced by dotted string in settings — not imported directly by users.

## Behaviours to implement

### Detector protocol

A detector is any callable matching:

```python
def my_detector(request: HttpRequest) -> bool:
    ...
```

Returns `True` if the request should skip the layout (return partial only). The engine calls each configured detector in order; if any returns `True`, partial mode is triggered.

### Built-in detectors

```python
# layouts/detection.py

def never_detector(request):
    """Default. Always returns False — layout always applied."""
    return False

def htmx_detector(request):
    """Returns True if request has HX-Request header."""
    return request.headers.get("HX-Request") == "true"

def query_param_detector(request):
    """Returns True if ?_partial=1 is in the query string."""
    return request.GET.get("_partial") == "1"
```

### Configuration

```python
# settings.py
LAYOUTS_PARTIAL_DETECTORS = [
    "layouts.detection.never_detector",  # default — no partial detection
]
```

To enable HTMX support:

```python
LAYOUTS_PARTIAL_DETECTORS = [
    "layouts.detection.htmx_detector",
    "layouts.detection.query_param_detector",
]
```

Detectors are loaded once at startup (or first use). Invalid dotted paths raise `ImproperlyConfigured`.

### Integration with `@layout`

Before calling the view, the detector engine runs. If any detector returns `True`:
- `request.is_layout_partial = True`
- The view executes normally.
- The view's response is returned directly — no layout assembly.

If no detector fires:
- `request.is_layout_partial = False`
- Normal layout assembly proceeds.

`render_with_layout()` always assembles the full layout — it bypasses detection entirely. This is intentional and documented.

### `LayoutMixin`

```python
class DashboardView(LayoutMixin, TemplateView):
    layout_class = DefaultLayout             # class or dotted string
    layout_panels = {}                       # optional per-view panel overrides
    template_name = "dashboard/_partial.html"
```

`LayoutMixin` overrides `dispatch()`:
- Applies the same `layout_role`, `is_layout_partial`, `layout_context` setup as `@layout`.
- After the view's normal response is produced, passes it to the layout engine.
- Partial detection runs the same way.
- `TemplateResponse` is force-rendered before passing to the layout engine.
- `layout_class` accepts a class or dotted string — resolved via the same registry as `@layout`.
- `layout_panels` mirrors `@layout`'s `panels` kwarg.

The mixin should feel identical to `WagtailLayoutMixin` in naming and structure. Both use `layout_class`, both work with string refs. A developer familiar with one should immediately understand the other.

## Tests

### Detection

- `never_detector` — always returns False, layout always applied.
- `htmx_detector` — `HX-Request: true` header triggers partial mode.
- `query_param_detector` — `?_partial=1` triggers partial mode.
- Multiple detectors — any one firing is sufficient.
- Partial mode: view executes, response returned directly, no layout assembly.
- `render_with_layout()` — detection does not run; layout always assembled.
- Invalid detector path in settings — `ImproperlyConfigured` at startup.

### LayoutMixin

- CBV with `layout_class` — full page assembled correctly.
- CBV with `layout_panels` — panel override applied.
- CBV with dotted string `layout_class` — resolved via registry.
- `TemplateResponse` from CBV — force-rendered before layout assembly.
- Partial detection fires on CBV request — partial returned, no layout.
- Missing `layout_class` — `ImproperlyConfigured` raised.

## What this phase does NOT include

The full Wagtail integration (`WagtailLayoutMixin`) — that's Phase 6. This phase only covers Django CBVs.

> **Agent implementation note (Phase 5 complete):**
> - `dj_layouts/detection.py` — `never_detector`, `htmx_detector`, `query_param_detector`; lazy `_get_detectors()` loader; `is_partial_request()`; `LAYOUTS_DETECTOR_RAISE_EXCEPTIONS` setting; `_reset_detector_cache()` for tests
> - `dj_layouts/mixins.py` — `LayoutMixin` with `async def dispatch` + `view_is_async = True`; handles sync and async handler methods; force-renders `TemplateResponse` in both partial and full paths; `LAYOUTS_PARTIAL_DETECTORS` detection wired in; `layout_class` accepts class or dotted string; `layout_panels` mirrors `@layout`'s `panels=`
> - `dj_layouts/decorators.py` — detection wired into `@layout` (sync) and `@async_layout`; `is_partial_request()` called before the view runs; `request.is_layout_partial` set in both branches
> - `dj_layouts/__init__.py` — `LayoutMixin` exported
> - `tests/test_detection.py` — 19 tests: built-in detectors, `is_partial_request`, multiple detectors, invalid path, exception handling, `@layout`/`@async_layout` integration, `render_with_layout` bypass
> - `tests/test_mixins.py` — 11 tests: basic assembly, dotted string, panel override, missing layout_class, async handlers, panel-role pass-through, TemplateResponse, non-200, partial detection (fires/doesn't), `view_is_async`
> - `docs/partial-detection.md` — full reference page; `docs/settings.md` updated; `mkdocs.yml` nav updated
> - Note for Phase 6 (Wagtail): `LayoutMixin` is the direct template for `WagtailLayoutMixin`. Both use `layout_class` (class or dotted string), `layout_panels`, and `async def dispatch`. Wagtail adds `get_layout_panels()` for context-aware panel selection and may need `wagtail_serve()` compatibility. The dotted-string resolution (`<app_label>.<ClassName>`) is handled by `Layout.resolve()` — Phase 6 can reuse this directly.

