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

## Future settings

The following settings are **not yet implemented** and are listed here as a reference for future versions:

- `LAYOUTS_PARTIAL_DETECTORS` — list of partial detector classes (planned)
- `LAYOUTS_CACHE_ENABLED` — enable panel-level caching (planned)
- `LAYOUTS_CACHE_BACKEND` — cache backend for panel caching (planned)

Do not configure these settings in the current version — they have no effect.
