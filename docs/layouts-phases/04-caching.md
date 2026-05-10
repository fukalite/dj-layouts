# Phase 4 — Panel Caching

> **Prerequisites:** Phase 2 complete (Phase 3 is independent — can be done before or after). Read [`docs/layouts-plan.md`](../layouts-plan.md) §"Panel Caching". Read [`docs/layouts-phases/00-overview.md`](./00-overview.md).
>
> **Before starting:** Discuss this phase with the user. Clarify cache key construction, how `cache.per_user` identifies the user (pk? username?), and whether cache misses should be logged. Do not write production code until you have a failing test.

## Goal

Individual panels can be cached using Django's cache framework. A panel whose output is cached is not re-rendered on subsequent requests — its stored HTML is used directly. Caching is opt-in, per-panel, configured in the `Panel()` declaration.

## Scope

### Files to create/modify

```
src/layouts/
    cache.py              # New: CacheConfig, cache shortcut functions
    panels.py             # Modified: pass CacheConfig through to rendering
    rendering.py          # Modified: activate cache check/write stubs from Phase 2
    __init__.py           # Modified: export cache module
    tests/
        test_cache.py     # New
```

### Public API additions

```python
from layouts import cache

cache.sitewide(timeout=3600)
cache.per_user(timeout=300)
cache.per_user_per_path(timeout=60)
cache.custom(key_func=my_func, timeout=120, backend="redis")
```

## Behaviours to implement

### `CacheConfig` dataclass

```python
@dataclass
class CacheConfig:
    key_func: Callable[[HttpRequest], str]
    timeout: int
    backend: str = "default"          # maps to CACHES setting key
    stale_ttl: int = 0                # reserved — no-op in v1
    refresh_func: Callable | None = None  # reserved — no-op in v1
```

`stale_ttl` and `refresh_func` are present on the dataclass but do nothing. Their presence stabilises the interface for future stale-while-revalidate support.

### Cache shortcuts

Each shortcut returns a `CacheConfig` with a pre-built `key_func`:

| Shortcut | Key includes |
|---|---|
| `cache.sitewide(timeout)` | panel name only |
| `cache.per_user(timeout)` | panel name + `request.user.pk` |
| `cache.per_user_per_path(timeout)` | panel name + user pk + `request.path` |
| `cache.custom(key_func, timeout, backend)` | whatever `key_func(request)` returns |

Keys are prefixed with `"layouts:panel:"` to avoid collisions with other Django cache users.

### Cache check/write in the render path

For each panel that has a `CacheConfig`:

1. Before rendering: `await cache.aget(key)` — if hit, use stored HTML, skip panel view entirely.
2. After rendering: `await cache.aset(key, html, timeout=config.timeout)` — store for next time.

This activates the stubs left in `rendering.py` during Phase 2.

### Settings

```python
LAYOUTS_CACHE_ENABLED = True   # False disables all panel caching globally
LAYOUTS_CACHE_BACKEND = "default"  # fallback backend if Panel doesn't specify one
```

When `LAYOUTS_CACHE_ENABLED = False`, the cache check/write is skipped entirely — panels always re-render. Useful for testing and development.

### What is cached

The **rendered HTML string** of the panel. Not the response object. Not the context. Just the final HTML output of the panel view.

### What is NOT cached

- The main view's output (only panels are cached).
- Render queue items (scripts/styles added by a cached panel are not replayed from cache — see note below).

> **Render queue + cache interaction:** This is a known limitation in v1. If a panel is cached, its HTML is returned from cache but its `add_script` / `add_style` calls are not replayed. For v1, document this clearly: panels that use render queues should not be cached, or the scripts/styles should be declared at the Layout level instead. Do not try to solve this in v1.

## Tests

- Panel with `cache.sitewide()` — second request returns cached HTML, panel view not called again.
- Panel with `cache.per_user()` — different users get different cache entries.
- `LAYOUTS_CACHE_ENABLED = False` — caching disabled globally, panel always re-renders.
- Cache miss → render → cache write (verify write happens).
- `stale_ttl` and `refresh_func` on `CacheConfig` — present but silently ignored (no error).
- Custom `key_func` — used for cache key construction.

## What this phase does NOT include

Stale-while-revalidate (deferred). Cache invalidation helpers (deferred). Render queue + cache integration (known v1 limitation, document only).

## Note for next agent

After completing this phase, leave a brief note here describing anything discovered that affects remaining phases.
