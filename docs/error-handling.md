# Error Handling

When a panel raises an exception, dj-layouts catches it, logs it, and calls your `on_panel_error()` hook. The rest of the page renders normally with a fallback in the failed panel's slot.

## Debug vs production mode

Behaviour differs based on whether debug mode is active (controlled by `LAYOUTS_DEBUG_ERRORS` — see [Settings](settings.md)):

| Mode | Behaviour |
|---|---|
| **Debug** | `PanelRenderError` is raised → Django's full error page appears |
| **Production** | Exception is logged, `on_panel_error()` is called, its return value fills the panel |

In debug mode, `on_panel_error()` is **bypassed entirely** — you always see the real exception and traceback.

## `PanelError`

`PanelError` is a dataclass (not an exception) that carries information about a panel failure. It's passed to `on_panel_error()`:

```python
from dj_layouts.errors import PanelError

@dataclass
class PanelError:
    panel_name: str        # name of the failed panel ("sidebar", "footer", etc.)
    source: object         # the Panel's source (URL name, callable, etc.)
    exception: BaseException  # the original exception
    traceback_str: str     # formatted traceback (from traceback.format_exc())
```

## `PanelRenderError`

`PanelRenderError` is the exception raised in debug mode. It wraps a `PanelError`:

```python
from dj_layouts.errors import PanelRenderError

class PanelRenderError(Exception):
    panel_error: PanelError  # access the full PanelError here
```

The exception message includes the panel name and original exception:

```
PanelRenderError: Panel 'sidebar' failed: ConnectionRefusedError(...)
```

## `on_panel_error()` hook

Override `on_panel_error()` on your Layout class to customise error handling in production:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"

    def on_panel_error(self, request, error):
        # error.panel_name, error.source, error.exception, error.traceback_str
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            "Panel %r failed: %s",
            error.panel_name,
            error.exception,
            exc_info=error.exception,
        )
        return ""  # return empty string to silently suppress the panel
```

The return value is used as the panel's HTML. Return:

- `""` — empty string (template fallback content will be used)
- An HTML string — shown in the panel's slot (e.g. an error message)

### Default behaviour

The default `on_panel_error()`:

1. Logs the error at `ERROR` level (with panel name, exception, and traceback)
2. Renders `self.error_template` (`"layouts/error.html"` by default)
3. Returns the rendered HTML (or `""` if rendering the error template also fails)

The shipped `layouts/error.html` shows a collapsible details box with the panel name, source, exception, and traceback.

### Customising the error template

The simplest customisation is to replace the error template:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    error_template = "myapp/panel_error.html"
```

Your template receives an `error` context variable (a `PanelError` instance):

```html+django
{# myapp/panel_error.html #}
<div class="panel-error">
  <p>⚠ This section failed to load.</p>
  {# In production, don't expose error details to users #}
</div>
```

### Suppressing all errors silently

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"

    def on_panel_error(self, request, error):
        return ""  # panel slot is empty; template fallback renders
```

### Sending errors to an external service

```python
import sentry_sdk

class DefaultLayout(Layout):
    template = "myapp/layout.html"

    def on_panel_error(self, request, error):
        sentry_sdk.capture_exception(error.exception)
        return ""
```

## Non-200 panel responses

If a panel view returns a non-200 HTTP response (e.g. a redirect, 404, or 403), it is treated as an error in async mode — the response object doesn't contain the expected HTML content, so the layout engine raises a `TypeError` when trying to extract the content string. This triggers `on_panel_error()` in production or `PanelRenderError` in debug mode.

!!! tip "Panel views should always return 200"
    Panel views should return a 200 response with their HTML fragment. If a panel has nothing to show, return `HttpResponse("")` or just `HttpResponse()` — not a redirect or error response. Use the template fallback for the "nothing to show" case.

## Async error isolation

Under `@async_layout`, panels run concurrently via `asyncio.gather(..., return_exceptions=True)`. A failing panel:

- Does **not** cancel other panels
- Does **not** prevent the page from rendering
- Has `on_panel_error()` called for its slot

Other panels complete and their output is used normally. The page renders with an error fallback only in the failed panel's slot.

## Example: different error strategies per layout

```python
class PublicLayout(Layout):
    """Public-facing layout — hide all errors from users."""
    template = "public/layout.html"

    def on_panel_error(self, request, error):
        logger.error("Panel %s failed", error.panel_name, exc_info=error.exception)
        return ""  # silent — no visible indication of failure

class AdminLayout(Layout):
    """Admin layout — show a visible error indicator."""
    template = "admin/layout.html"
    error_template = "admin/panel_error.html"
    # Uses default on_panel_error() which renders error_template
```
