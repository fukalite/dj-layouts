# Phase 1 — Synchronous Core

> **Prerequisites:** Read [`docs/layouts-plan.md`](../layouts-plan.md) in full, then [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Confirm the file structure, the public API shape, and any implementation details that feel underspecified. Do not write production code until you have a failing test.

## Goal

A working layout system that renders full pages synchronously. Panels are called sequentially. No caching, no render queues, no partial detection, no HTMX support. The result should be a system you could actually use in production for a simple site.

## Scope

### Files to create

```
src/layouts/
    __init__.py           # Public API exports for this phase (see below)
    apps.py               # LayoutsConfig — AppConfig + autodiscover_modules("layouts")
    base.py               # Layout base class + __init_subclass__ registry
    panels.py             # Panel class + source resolution
    decorators.py         # @layout, @panel_only
    errors.py             # PanelError, PanelRenderError
    rendering.py          # render_with_layout (sync only in this phase)
    context.py            # LayoutContext, FrozenLayoutContext
    request_utils.py      # clone_request_as_get
    autodiscover.py       # find + import layouts.py from installed apps
    templatetags/
        __init__.py
        layouts.py        # {% panel %}, {% endpanel %} only in this phase
    templates/
        layouts/
            _error.html   # Debug error panel output
    tests/
        __init__.py
        conftest.py
        test_base.py
        test_panels.py
        test_decorators.py
        test_rendering.py
        test_context.py
        test_templatetags.py
```

### Public API exported from `__init__.py` after this phase

```python
from layouts import (
    Layout,
    Panel,
    layout,        # decorator
    panel_only,    # decorator
    render_with_layout,
)
```

`cache`, `LayoutMixin`, `WagtailLayoutMixin`, queue functions — not yet.

## Behaviours to implement

### Registry and autodiscovery

- `Layout.__init_subclass__` registers every concrete subclass in a module-level registry keyed by `"<app_label>.<ClassName>"`.
- `LayoutsConfig.ready()` calls `autodiscover_modules("layouts")` so each installed app's `layouts.py` is imported at startup, triggering registration.
- The registry must support lookup by class reference (direct) and by dotted string (lazy). String resolution happens at first use, not at import time.

### Layout class

- `template` — required class attribute, path to the layout template.
- `get_layout_context(request)` — optional override, returns a dict merged into `request.layout_context`. Default returns `{}`.
- `on_panel_error(request, error: PanelError)` — optional override for error handling. Default logs and renders `_error.html` in DEBUG, renders empty string in production.
- Panel descriptors collected by `__init_subclass__` into `cls._panels: dict[str, Panel]`.

### Panel class and source resolution

`Panel(source, context=None, cache=None)` where source is one of:

| Type | Behaviour |
|---|---|
| `str` (URL name, e.g. `"core:navigation"`) | Resolved via `reverse()`, request cloned as GET, view called internally |
| Callable | Called directly with the cloned request + any kwargs |
| Plain string (not a URL name) | Returned as-is |
| `list` | Each item resolved independently, outputs concatenated |
| `None` | Empty string |

`context` dict is merged into the cloned request's layout context before calling the source. Source resolution must not import from project code — it uses `resolve()` for URL names.

### Request cloning

`clone_request_as_get(request)` produces a shallow copy with:
- `method` forced to `GET`
- `POST`, `FILES` cleared
- `layout_role` set to `"panel"`
- `is_layout_partial` set to `False`
- `layout_context` set to the frozen layout context
- Everything else preserved: `user`, `session`, `META`, `path`, `resolver_match`

### `@layout` decorator

- Accepts a `Layout` class or dotted string: `@layout(DefaultLayout)` / `@layout("myapp.DefaultLayout")`.
- Accepts optional `panels={}` kwarg for per-view panel overrides.
- Sets `request.layout_role = "main"` and `request.is_layout_partial = False` before calling the view.
- After the view returns, calls `render_with_layout()` to assemble the full page.
- If `request.layout_role` is already `"panel"` when the decorator runs, it is a no-op — returns the view's response directly. This allows the same view to be used as both a standalone page and a panel.
- If the view returns a `TemplateResponse`, force-renders it before passing to the layout engine.

### `@panel_only` decorator

- If `request.layout_role == "panel"`: passes through to the view.
- If called via URL (role not set or `"main"`): returns `HttpResponseForbidden(403)`.
- If applied to a view that is also decorated with `@layout`, raises `TypeError` at decoration time.

### `render_with_layout()`

```python
render_with_layout(request, layout_class, template_name, context=None, *, panels=None)
```

- Always renders the full layout. No partial detection in this phase.
- Resolves and calls each panel source sequentially.
- Renders the layout template with the assembled context.
- Returns `HttpResponse`.

### LayoutContext

- `LayoutContext` — `dict` subclass. Populated with Layout class defaults then `get_layout_context()` result, then set on `request.layout_context`.
- `FrozenLayoutContext` — same data, but `__setitem__`, `__delitem__`, `update`, `pop`, `clear`, `setdefault` raise `TypeError("layout_context is read-only in panel views")`.
- Freeze happens before any panel is called.

### Error handling

- `PanelError(panel_name, source, exception, traceback_str)` — dataclass, not an exception.
- `PanelRenderError` — actual exception, raised only in DEBUG mode when an error bubbles up.
- In DEBUG: bypass `on_panel_error`, raise `PanelRenderError` so Django's yellow error page shows.
- In production: call `on_panel_error`; default implementation logs the error and renders `_error.html` (or empty string if that also fails).

### Template tags (this phase only)

`{% panel "name" %}...fallback content...{% endpanel %}` — outputs the rendered panel content, or fallback if the panel is empty/absent.

### `LAYOUTS_DEBUG_ERRORS` setting

`None` (default) → follow `settings.DEBUG`. `True`/`False` → explicit override.

## Tests

Every behaviour above needs a test. Key scenarios:

- Layout with URL name panel, callable panel, string panel, list panel, None panel
- `@layout` no-ops when `layout_role == "panel"` (same view used in both roles)
- `@panel_only` returns 403 when not called as a panel
- `@panel_only` + `@layout` raises `TypeError` at decoration time
- `LayoutContext` is mutable in main view, frozen in panel views
- `on_panel_error` called on panel failure in non-DEBUG; `PanelRenderError` raised in DEBUG
- String ref (`@layout("app.MyLayout")`) resolves correctly
- Autodiscovery: a Layout in an app's `layouts.py` is registered on startup
- `{% panel %}` renders fallback when panel is empty

## What this phase does NOT include

Caching, render queues, async, partial detection, `LayoutMixin`, Wagtail support. If you find yourself reaching for any of these, stop — they belong in later phases.

## Note for next agent

### Implementation decisions made during Phase 1

**`request.layout_context` availability:**
- In the `@layout` decorator path, `layout_context` is NOT set on the request before the main view executes. It is set during `_assemble_layout`, after the view returns. This is intentional (two-pass rendering — main view is isolated). If a view needs layout context values at render time, use `render_with_layout` instead (which sets `layout_context` before rendering the template).
- In the `render_with_layout` path, `layout_context` IS set on request before `render_to_string`, so main templates can access `request.layout_context`.

**`POST`/`FILES` clearing in `clone_request_as_get`:**
- Uses `__dict__["_post"]` and `__dict__["_files"]` to bypass Django's lazy-parse properties. These are private attributes of `WSGIRequest`/`ASGIRequest`. Tested against Django 6.x. If a future Django version changes these internals, look at `request_utils.py` first.

**String panel source resolution (decided):**
- Positional string containing `:` → `reverse()`, `NoReverseMatch` propagates (no silent fallback)
- Positional string without `:` → literal content, `reverse()` never called
- `""` (empty string) → no output, same as `None`
- `Panel(url_name="name")` or `resolve_panel_source(request, url_name="name")` → always `reverse()`, even for bare names (escape hatch for non-namespaced URL names)
- `Panel(literal="text:with:colons")` or `resolve_panel_source(request, literal="...")` → always literal (escape hatch for content containing `:`)
- Future phases: document this API clearly in any user-facing docs. The `url_name=` / `literal=` kwargs on both `Panel` and `resolve_panel_source` are the stable public API for disambiguation.

**String panel source resolution (unresolved design question):**
~~See discussion in the session where Phase 1 was implemented.~~
*(Resolved above — implemented in Phase 1 follow-up commits.)*


**`error_template` attribute:**
- `Layout.error_template = "layouts/error.html"` (no leading underscore — convention is that templates are never private).
- Override on the Layout subclass to use a different template. Override `on_panel_error()` entirely for fully custom error handling.
- `on_panel_error` always renders `error_template` (no DEBUG guard). `LAYOUTS_DEBUG_ERRORS` is the setting that controls whether we ever reach `on_panel_error` at all. Set `LAYOUTS_DEBUG_ERRORS=False` locally to test error template rendering without turning off DEBUG globally.

**`@layout` decorator — layout_context and response pass-through:**
- `request.layout_context` IS set before the wrapped view executes (layout class is resolved and context built pre-view, same as `render_with_layout`). The decorator and `render_with_layout` are now fully equivalent in this regard.
- Non-200 responses (redirects, 404s, 403s, 500s) are passed through unchanged — the decorator does not wrap them in the layout. Same for `StreamingHttpResponse`.
- Remaining limitations: no Content-Type guard (a 200 JSON response would be inserted as layout content — don't use `@layout` on JSON views); no multi-decorator stacking support.

**`Panel.context` / `_call_url` — context overrides URL kwargs:**
- When a URL-based panel has extra context (`Panel("app:view", context={"pk": 5})`), that context is merged on top of URL-captured kwargs with panel context winning. This is intentional: it lets callers supply override values without having to construct a custom URL. Document this in any user-facing docs — it's a feature, not a footgun.
- The merge order is `**{**match.kwargs, **panel_context}` (panel wins). Future phases should preserve this.

**`Panel.join`:**
- When `panel.source` is a list, `panel.join` is the separator used to concatenate results. Default `""` (no separator). Forwarded as `_join` to `resolve_panel_source`.

