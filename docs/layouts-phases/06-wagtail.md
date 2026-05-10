# Phase 6 — Wagtail Integration + Layout Inheritance

> **Prerequisites:** Phase 1 complete. Phase 5 recommended (partial detection is used by `WagtailLayoutMixin`). Read [`docs/layouts-plan.md`](../layouts-plan.md) §"Wagtail Integration" and §"Layout inheritance". Read [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Clarify Wagtail preview mode behaviour, whether `WagtailLayoutMixin` should fall back gracefully when Wagtail is not installed, and the exact system check messages for inheritance mismatches. Do not write production code until you have a failing test.

## Goal

Two additions:

1. **`WagtailLayoutMixin`** — Wagtail `Page` subclasses can opt into the layout system via a `layout_class` attribute, following the same conventions as `LayoutMixin`.
2. **Layout inheritance** — verified, tested, documented behaviour for subclassing a Layout.

## Scope

### Files to create/modify

```
src/layouts/
    wagtail.py            # New: WagtailLayoutMixin (conditional import)
    base.py               # Modified: system checks for inheritance
    tests/
        test_wagtail.py   # New
        test_base.py      # Modified: inheritance tests
```

### Public API additions

```python
from layouts import WagtailLayoutMixin
```

`WagtailLayoutMixin` is exported from `__init__.py` only if Wagtail is installed (`try/except ImportError`). Importing it when Wagtail is absent raises `ImportError` with a clear message.

## Behaviours to implement

### `WagtailLayoutMixin`

```python
from layouts import WagtailLayoutMixin

class BlogPage(WagtailLayoutMixin, Page):
    layout_class = BlogLayout           # class or dotted string
    template = "blog/_content.html"    # Partial — no {% extends %}

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["posts"] = self.get_children().live()
        return context
```

The mixin overrides Wagtail's `serve()` method:

1. Run partial detection (same engine as Phase 5). If triggered, call `super().serve()` — normal Wagtail behaviour returns the partial page template.
2. Otherwise: render the page template as a partial (call `page.get_template()` + `page.get_context()`), then pass the rendered partial to the Layout for full-page assembly.

**Preview mode:** if `request.is_preview` is `True`, skip layout assembly and render the page normally. Preview should show the page content without layout composition, so editors see exactly what the template produces.

**Attribute conventions:**
- `layout_class` — same as `LayoutMixin`. Class or dotted string.
- `layout_panels` — same as `LayoutMixin`. Optional per-page panel overrides.
- `template` — Wagtail's existing attribute. Points to a partial template (no `{% extends %}`).

The mixin must be placed before `Page` in the MRO: `class BlogPage(WagtailLayoutMixin, Page)`.

### Layout inheritance

The following must work correctly and be covered by tests:

```python
class DefaultLayout(Layout):
    template = "layouts/default.html"
    navigation = Panel("core:navigation")
    sidebar = Panel(render_sidebar)
    footer = Panel("<p>© 2026</p>")

class AdminLayout(DefaultLayout):
    template = "layouts/admin.html"    # Override template
    sidebar = Panel(render_admin_sidebar)  # Override one panel
    # navigation + footer inherited via __init_subclass__ MRO walk
```

**What must hold:**
- `AdminLayout._panels` contains `navigation` (from parent), `sidebar` (overridden), `footer` (from parent).
- `AdminLayout` is registered in the registry independently of `DefaultLayout`.
- `AdminLayout.template` is `"layouts/admin.html"`.
- `get_layout_context()` follows standard Python MRO — child calls `super()` if it wants to merge.
- `on_panel_error()` follows standard Python MRO — child can override without calling super.
- Render queues (`ScriptQueue` etc.) declared on a parent are inherited by subclasses.

**Panel removal:** not supported in v1. Document that if a subclass doesn't want a parent's panel, use a different base class. Do not add a `Panel.REMOVED` sentinel.

**Unrendered panel warning:** if `AdminLayout._panels` contains a panel whose name does not appear in any `{% panel %}` tag in the template — no warning in v1. Document the limitation.

### System checks

Add Django system checks (in `apps.py` `ready()` or a dedicated `checks.py`):

- `@layout("app.DoesNotExist")` — error at startup if the string ref doesn't resolve to a registered Layout.
- `layout_class = "app.DoesNotExist"` on a `LayoutMixin` or `WagtailLayoutMixin` subclass — same check.
- `layout_class` pointing at a class that is not a `Layout` subclass — error with clear message.

## Tests

### Wagtail

- `BlogPage` with `WagtailLayoutMixin` — `serve()` returns full layout-assembled page.
- Partial detection fires — `serve()` returns partial (normal Wagtail response).
- `request.is_preview = True` — layout assembly skipped, normal Wagtail preview response.
- String ref `layout_class` — resolved via registry.
- `layout_panels` override applied.
- `WagtailLayoutMixin` import when Wagtail not installed — `ImportError` with clear message.

### Layout inheritance

- Subclass inherits parent panels.
- Subclass panel override shadows parent's.
- Subclass registered separately in registry.
- `get_layout_context()` via `super()` merges parent and child context.
- Render queues inherited from parent.
- Panel removal not supported — no `Panel.REMOVED`, no error if user tries `sidebar = None` (None is a valid source, renders empty).

### System checks

- Invalid string ref in `@layout` — system check error at startup.
- Invalid string ref in `layout_class` — system check error at startup.
- `layout_class` pointing at a non-Layout class — system check error.

## What this phase does NOT include

Nested layouts (deferred). Unrendered panel warnings (deferred). Panel removal (deferred). All in the "Deferred to Future Versions" section of the main plan.

## Note for next agent

This is the final v1 phase. After completing it, the full v1 feature set is implemented. Leave a note here summarising:
- Any known rough edges discovered during implementation.
- Anything that should be addressed before package extraction.
- Suggested first items for a v2 milestone.
