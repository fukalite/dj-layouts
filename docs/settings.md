# Settings

dj-layouts settings are defined in your Django `settings.py`. All settings are optional; sensible defaults apply.

## `LAYOUTS_DEBUG_ERRORS`

**Type:** `bool | None`  
**Default:** `None`

Controls whether panel rendering errors raise a `PanelRenderError` exception (showing Django's debug error page) or are handled gracefully by `on_panel_error()`.

| Value | Behaviour |
|---|---|
| `None` (default) | Follows Django's `DEBUG` setting |
| `True` | Always raise `PanelRenderError` (debug mode, regardless of `DEBUG`) |
| `False` | Always call `on_panel_error()` (production mode, even when `DEBUG = True`) |

### Debug mode behaviour

When `LAYOUTS_DEBUG_ERRORS` resolves to `True`:

- `on_panel_error()` is **not called**
- A `PanelRenderError` exception is raised immediately
- Django's standard error page appears with the full traceback

This makes it easy to spot panel failures during development — you get the real exception, not a silently swallowed error.

### Production mode behaviour

When `LAYOUTS_DEBUG_ERRORS` resolves to `False`:

- The exception is **logged automatically** at `ERROR` level
- `on_panel_error()` is called with a `PanelError` dataclass
- The return value of `on_panel_error()` is used as the panel's HTML
- The page renders with an error fallback in the failed panel's slot

### Examples

```python
# settings.py

# Default — follows DEBUG:
# LAYOUTS_DEBUG_ERRORS is not set (or set to None)

# Force debug behaviour in staging (DEBUG might be False):
LAYOUTS_DEBUG_ERRORS = True

# Force production behaviour locally to test error handling:
LAYOUTS_DEBUG_ERRORS = False
```

### Relationship with `DEBUG`

```
LAYOUTS_DEBUG_ERRORS = None   and   DEBUG = True   →  debug mode  (raises PanelRenderError)
LAYOUTS_DEBUG_ERRORS = None   and   DEBUG = False  →  production  (calls on_panel_error)
LAYOUTS_DEBUG_ERRORS = True   (any DEBUG)          →  debug mode  (raises PanelRenderError)
LAYOUTS_DEBUG_ERRORS = False  (any DEBUG)          →  production  (calls on_panel_error)
```

See [Error Handling](error-handling.md) for details on `on_panel_error()`, `PanelError`, and `PanelRenderError`.

---

## `LAYOUTS_CACHE_ENABLED`

**Type:** `bool`  
**Default:** `True`

When set to `False`, all panel caching is disabled globally — panels always re-render even when a `cache=` argument is provided in their `Panel(...)` definition.

This is useful in development or testing where you want predictable, uncached behaviour:

```python
# settings/local.py
LAYOUTS_CACHE_ENABLED = False
```

Note that this setting does not affect Django's own cache framework — it only controls whether dj-layouts writes to or reads from the cache for panel results.

---

## `LAYOUTS_CACHE_BACKEND`

**Type:** `str`  
**Default:** `"default"`

The name of the Django cache backend used as the default for panel caching when no `backend=` is specified on the `CacheConfig`. Must be a key in `settings.CACHES`.

```python
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "panels":  {"BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache", ...},
}

LAYOUTS_CACHE_BACKEND = "panels"
```

Individual panels can always override the backend per-panel:

```python
Panel("myapp:nav", cache=cache.sitewide(timeout=3600, backend="panels"))
```

---

## `LAYOUTS_PARTIAL_DETECTORS`

**Type:** `list[str]`  
**Default:** `[]`

A list of dotted import paths to partial detector callables. Each detector receives the current request and returns `True` if the request should skip layout assembly and return only the partial view response.

```python
LAYOUTS_PARTIAL_DETECTORS = [
    "dj_layouts.detection.htmx_detector",
    "dj_layouts.detection.query_param_detector",
]
```

Built-in detectors:
- `dj_layouts.detection.never_detector` — always `False` (layout always assembled)
- `dj_layouts.detection.htmx_detector` — `True` when `HX-Request: true` header is present
- `dj_layouts.detection.query_param_detector` — `True` when `?_partial=1` is in the query string

Detectors are loaded lazily on first request. An invalid path raises `ImproperlyConfigured`.

See [Partial Detection](partial-detection.md) for the full reference.

---

## `LAYOUTS_DETECTOR_RAISE_EXCEPTIONS`

**Type:** `bool`  
**Default:** `False`

When `False` (default), exceptions raised inside a detector are logged at `WARNING` level and the detector is treated as returning `False`. Layout assembly proceeds normally.

When `True`, detector exceptions propagate as-is. Useful in development to catch broken detectors immediately.

```python
# settings/local.py
LAYOUTS_DETECTOR_RAISE_EXCEPTIONS = True
```

---

## Future settings

The following settings are **not yet implemented** and are listed here as a reference for future versions:

- `LAYOUTS_PARTIAL_DETECTORS` — list of partial detector classes (planned)

Do not configure this setting in the current version — it has no effect.
