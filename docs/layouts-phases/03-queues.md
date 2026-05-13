# Phase 3 — Render Queues

> **Prerequisites:** Phase 2 complete. Read [`docs/layouts-plan.md`](../layouts-plan.md) §"Render Queues". Read [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Clarify the exact deduplication semantics, the template tag syntax for block-style inline content, and how queues interact with concurrent panel rendering. Do not write production code until you have a failing test.

## Goal

Views and templates can register scripts, styles, and arbitrary content into named queues. After all panels render, the layout template renders each queue's contents once, deduplicated, in a deterministic order.

## Scope

### Files to create/modify

```
src/layouts/
    queues.py             # New: ScriptQueue, StyleQueue, RenderQueue, ScriptItem, StyleItem
    rendering.py          # Modified: collect queues after gather, merge in panel-definition order
    request_utils.py      # Modified: attach empty queue instances to cloned panel requests
    __init__.py           # Modified: export add_script, add_style, add_to_queue
    templatetags/
        layouts.py        # Modified: add {% addscript %}, {% addstyle %}, {% enqueue %},
                          #           {% renderscripts %}, {% renderstyles %}, {% renderqueue %}
    tests/
        test_queues.py    # New
        test_templatetags.py  # Modified: add queue tag tests
```

### Public API additions

```python
from layouts import add_script, add_style, add_to_queue
```

## Behaviours to implement

### Data model

```python
@dataclass(frozen=True)
class ScriptItem:
    src: str | None = None
    inline: str | None = None
    is_async: bool = False
    is_deferred: bool = False
    type: str = ""

@dataclass(frozen=True)
class StyleItem:
    href: str | None = None
    inline: str | None = None
    media: str = ""
```

Frozen dataclasses are hashable by default — deduplication uses a `set` for seen-tracking, a `list` for order preservation.

### Queue types

**`ScriptQueue`** — knows how to render `<script>` tags (src, inline, async, defer, type attributes). No user-supplied template.

**`StyleQueue`** — knows how to render `<link rel="stylesheet">` and `<style>` tags. No user-supplied template.

**`RenderQueue(template="...")`** — generic. User supplies a template that receives `items` (list of strings) in context.

All three share a common `BaseQueue` with `add(item)` deduplication logic.

### Functions (view-side API)

```python
add_script(request, src=None, *, inline=None, is_async=False, is_deferred=False, type="")
add_style(request, href=None, *, inline=None, media="")
add_to_queue(request, queue_name: str, item: str)
```

These append to queues attached to `request`. Panel requests get their own queue instances (attached during clone); after `asyncio.gather`, the rendering engine merges all panel queues into the main queues in panel-definition order.

### Template tags (adding-side)

```
{% addscript "/static/js/chart.js" %}
{% addscript "/static/js/chart.js" async %}
{% addscript "/static/js/chart.js" defer %}
{% addscript %}
  document.addEventListener('DOMContentLoaded', init);
{% endaddscript %}

{% addstyle "/static/css/chart.css" %}
{% addstyle "/static/css/chart.css" media="print" %}
{% addstyle %}
  .chart { color: red; }
{% endaddstyle %}

{% enqueue "head_extras" %}
<meta name="robots" content="noindex">
{% endenqueue %}
```

### Template tags (rendering-side)

```
{% renderscripts %}    {# outputs all <script> tags #}
{% renderstyles %}     {# outputs all <link>/<style> tags #}
{% renderqueue "head_extras" %}  {# outputs generic queue via its template #}
```

These are no-ops if the corresponding queue has no items.

### Deduplication

`BaseQueue.add(item)` checks `item in self._seen` before appending. Since items are frozen dataclasses (or strings for `RenderQueue`), hash comparison is O(1).

Duplicate `/static/js/chart.js` added by three different panels → rendered once.

### Ordering

After `asyncio.gather`, the rendering engine iterates panels in definition order and merges each panel's queues into the layout's queues. Within each panel's contribution, insertion order is preserved. The net effect: items from Panel A (defined first) all precede items from Panel B, in the order they were added within each panel.

### Queue availability

Queue instances are attached to `request.layout_queues: dict[str, BaseQueue]`. Layout-level `ScriptQueue`, `StyleQueue`, and `RenderQueue` instances are declared on the Layout class and registered by name at class definition. Accessing an undefined queue name in `add_to_queue` raises `KeyError` with a helpful message.

## Tests

- `add_script` in a view — script appears in `{% renderscripts %}` output.
- `add_style` in a template — style appears in `{% renderstyles %}` output.
- Duplicate script added by two panels — rendered once.
- Panel A and Panel B both add scripts — order follows panel definition order, not execution order.
- `RenderQueue` with user template — items passed to template context as `items`.
- `{% renderscripts %}` no-ops when queue is empty.
- Inline script block tag — content rendered inside `<script>` tags.

## What this phase does NOT include

Caching, partial detection, `LayoutMixin`, Wagtail. Queue priority buckets (prepend/append) are deferred — see main plan.

## Note for next agent

Phase 3 is complete. Implementation notes for Phases 4–6:

- **Queue ordering — content before panels**: The main view's queue contributions (via `add_script` / template tags in the content template) always precede panel contributions, because `layout_queues` is attached to the request before the content template renders, and panels are merged after `asyncio.gather`. **This should be documented in `docs/` before Phase 4.** Users who need a panel's scripts to precede the content's scripts cannot currently achieve this — queue priority buckets (prepend/append) were deliberately deferred.

- **`@layout` decorator sets up queues**: `request.layout_queues` is attached in the `@layout` / `@async_layout` wrappers (before the view function runs), and also at the start of `render_with_layout` / `async_render_with_layout`. Both paths converge on `_assemble_layout` / `_async_assemble_layout`, which do **not** recreate queues — they rely on queues already being present on the request.

- **`RenderQueue` templates must use `{{ item|safe }}`**: Items are raw strings (HTML fragments). Django's auto-escaping will escape them unless the user's template marks them safe. This is the correct Django pattern and should be noted in the public docs.

- **Queue names are user-defined**: `ScriptQueue` / `StyleQueue` / `RenderQueue` instances are class attributes on the Layout subclass. The conventional names are `scripts` and `styles` (matching `{% renderscripts %}` / `{% renderstyles %}`). `{% renderqueue "name" %}` works for any queue name. There is no global registry of queue types — discovery happens via `__init_subclass__`.

- **Other work to do (carry to Phases 4–6)**: Queue priority buckets (prepend vs append), per-queue dedup key customisation, and the ability to control where the content view's queue contributions fall relative to panel contributions are all deferred. Flag these as future work in the public docs.
