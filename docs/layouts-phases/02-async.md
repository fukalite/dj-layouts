# Phase 2 — Async Rendering

> **Prerequisites:** Phase 1 complete. Read [`docs/layouts-plan.md`](../layouts-plan.md) §"Async Rendering" and [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Confirm the async strategy, sync-wrapping approach, and how errors from `asyncio.gather` should surface. Do not write production code until you have a failing test.

## Goal

Replace sequential panel rendering with concurrent rendering via `asyncio.gather`. The change should be transparent to users — no API changes, just faster page assembly under ASGI. Sync panel views continue to work via automatic `sync_to_async` wrapping.

## Scope

### Files to modify

```
src/dj_layouts/
    panels.py             # async_resolve_panel_source, _async_resolve_string_source, _async_call_url
    rendering.py          # _async_assemble_layout, async_render_with_layout
    decorators.py         # @async_layout
    __init__.py           # export async_render_with_layout, async_layout, async_resolve_panel_source
    tests/
        test_async.py     # New file
```

### Public API added in this phase

```python
from dj_layouts import (
    async_render_with_layout,    # async equivalent of render_with_layout
    async_layout,                # async equivalent of @layout decorator
    async_resolve_panel_source,  # async equivalent of resolve_panel_source (public for custom use)
)
```

**Choosing between sync and async entry points:**
Users must explicitly choose the right entry point for their deployment:
- **WSGI / sync-only projects**: use `@layout` and `render_with_layout`. Zero async overhead.
- **ASGI projects with async views**: use `@async_layout` and `async_render_with_layout`. Panels run concurrently via `asyncio.gather`.

There is no automatic switching between the two paths. A sync project that imports only
`@layout` will never touch the async code path.

## Behaviours to implement

### Rendering order guarantee

The render sequence must remain deterministic:

1. Main view executes → produces content, writes to `layout_context`, enqueues items (queues not yet in this phase, but the ordering contract must hold for when they arrive).
2. `layout_context` is frozen (before any panel runs).
3. All panel views execute **concurrently** via `asyncio.gather(return_exceptions=True)`.
4. Panel results are collected in **panel-definition order** (the order panels appear on the Layout class), regardless of which panel finished first.
5. Layout template renders synchronously with all outputs assembled.

### Sync view detection and wrapping

- Detect sync panel callables via `asyncio.iscoroutinefunction()`.
- Wrap sync callables with `asgiref.sync.sync_to_async` before passing to `asyncio.gather`.
- Wrap sync URL-resolved views the same way.
- Do not double-wrap already-async views.

### Error isolation

`asyncio.gather(return_exceptions=True)` — a failing panel returns its exception rather than crashing the gather. The rendering engine must:
- Collect results in definition order.
- For each result that is an exception, construct a `PanelError` and call `on_panel_error` (same as Phase 1 behaviour, now in an async context).

### Cache compatibility (for Phase 4)

The async render path should already use `await cache.aget()` / `await cache.aset()` at the cache call sites — even though caching is not implemented yet. This means the cache hook points exist in `rendering.py` as commented stubs, ready for Phase 4 to activate without restructuring.

### Template rendering

Django's template engine is synchronous. The final layout template render (and the
content template render in `async_render_with_layout`) calls `render_to_string` directly —
no `sync_to_async` wrapper.

**Why not `sync_to_async`?** Template rendering is CPU-bound, not I/O-bound. Wrapping it
in `sync_to_async` would push it to a thread pool, adding thread-overhead for something
that doesn't benefit from concurrency. Django's own async views (e.g., `TemplateView`)
call `render_to_string` directly for the same reason. The only scenario where this would
be a concern is if a template tag performs ORM access — but that is already an antipattern
and `sync_to_async` would not eliminate the blocking, only defer it to a thread.

## Tests

- Two panels run concurrently (verify via timing or mocking — concurrent execution, not sequential).
- A slow async panel does not block other panels.
- A sync panel view is wrapped automatically and runs correctly.
- Panel results are assembled in definition order, not completion order.
- A failing panel triggers `on_panel_error`; other panels still complete.
- The full render works under ASGI (use `pytest-asyncio` or Django's async test client).

## What this phase does NOT include

Caching, render queues, partial detection. The cache stubs in `rendering.py` are comments only.

## Note for next agent

After completing this phase, leave a brief note here describing anything discovered that affects Phases 3–6.

---

**Completed.** Key decisions and discoveries for future phases:

1. **Two explicit paths, no auto-detection.** Sync (`@layout`, `render_with_layout`) and async
   (`@async_layout`, `async_render_with_layout`) are separate entry points. There is no runtime
   detection of WSGI vs ASGI — users choose explicitly. Phase 3+ should maintain this split.

2. **`render_to_string` called directly in async path.** Both `async_render_with_layout` and
   `_async_assemble_layout` call `render_to_string` synchronously (no `sync_to_async`). This is
   intentional — template rendering is CPU-bound, not I/O-bound. See `§ Template rendering` above.

3. **Cache stubs not present.** The phase spec mentioned adding commented cache stubs in
   `rendering.py`. They were not added in this phase. Phase 4 (caching) will need to insert
   `await cache.aget()` / `await cache.aset()` hooks around the `async_resolve_panel_source`
   calls in `_async_assemble_layout`, and equivalent sync hooks in `_assemble_layout`. The
   natural hook points are per-panel, just before/after the `create_task` call in the async path
   and just before/after `resolve_panel_source` in the sync path.

4. **`FrozenLayoutContext` is applied on `clone_request_as_get`.** Panel requests receive a
   frozen (read-only) copy of `layout_context` via `request_utils.clone_request_as_get`. This
   contract must be preserved in Phase 3 (partial detection / render queues) when panel requests
   are constructed.

5. **List sources run concurrently within a panel.** When a `Panel` source is a list, the async
   path resolves all list items via `asyncio.gather` concurrently. This is in addition to the
   top-level panel concurrency. Phase 3+ docs should mention this.

6. **`@async_layout` rejects sync views at decoration time.** Applying `@async_layout` to a
   sync function raises `TypeError` immediately. This is intentional — it prevents silent bugs
   where a sync view appears to work but blocks the event loop.
