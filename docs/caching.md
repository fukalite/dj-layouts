# Panel Caching

dj-layouts provides per-panel caching via Django's cache framework. When a panel is cached, its HTML is stored and returned directly on subsequent requests — the panel view is not re-executed. Render queue items (scripts, styles) that the panel would have enqueued are cached alongside the HTML and replayed on cache hits.

## Setup

Import the `cache` module and add a `cache=` argument to your `Panel`:

```python
from dj_layouts import Layout, Panel, cache

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    nav = Panel("myapp:nav", cache=cache.sitewide(timeout=3600))
```

That's all. The first request renders the panel and writes to cache. Subsequent requests serve the stored HTML without calling the panel view.

## Cache strategies

### `cache.sitewide(timeout, *, backend="default")`

One cache entry shared by all users and all paths. Best for panels whose output never varies per-user or per-URL — site navigation, global footers, promotional banners.

```python
nav = Panel("myapp:nav", cache=cache.sitewide(timeout=3600))
```

### `cache.per_user(timeout, *, backend="default")`

Separate cache entries per authenticated user. The cache key includes `user.pk`. Anonymous users (where `user.is_authenticated` is `False`) all share a single entry keyed as `"anonymous"`.

```python
account_nav = Panel("myapp:account_nav", cache=cache.per_user(timeout=900))
```

!!! warning "All anonymous users share one cache entry"
    With `cache.per_user()`, every unauthenticated visitor shares the same cached output. If anonymous panel output can vary by any request attribute (cookie, query parameter, session value), use `cache.custom()` with an explicit `key_func` instead.

### `cache.per_path(timeout, *, backend="default")`

Separate cache entries per request path (`request.path`). Useful for panels that render differently on different pages but are the same for all users on that page.

```python
breadcrumbs = Panel("myapp:breadcrumbs", cache=cache.per_path(timeout=300))
```

### `cache.per_user_per_path(timeout, *, backend="default")`

Combines user identity and request path. Each user+path combination gets its own entry. Suitable for user-specific, page-sensitive widgets.

```python
sidebar = Panel("myapp:sidebar", cache=cache.per_user_per_path(timeout=300))
```

### `cache.per_session(timeout, *, backend="default")`

Separate cache entries per Django session key (`request.session.session_key`). When the session key is absent the key component falls back to `"no-session"`.

```python
cart_summary = Panel("myapp:cart_summary", cache=cache.per_session(timeout=60))
```

### `cache.custom(key_func, timeout, *, backend="default")`

Full control over the cache key. `key_func` receives the request and must return a string. The returned string is appended to the base key:

```python
def vary_by_currency(request):
    return request.session.get("currency", "USD")

price_panel = Panel("myapp:price", cache=cache.custom(key_func=vary_by_currency, timeout=600))
```

If `key_func` returns an empty string the entry is sitewide (same as `cache.sitewide()`).

## Cache key format

Keys follow this format:

```
layouts:panel:{panel_name}              # sitewide (no vary)
layouts:panel:{panel_name}:{vary}       # all other strategies
```

For example:

| Strategy | Panel name | Vary | Key |
|---|---|---|---|
| `sitewide` | `nav` | — | `layouts:panel:nav` |
| `per_user` | `nav` | user pk `42` | `layouts:panel:nav:42` |
| `per_user` | `nav` | anonymous | `layouts:panel:nav:anonymous` |
| `per_path` | `nav` | `/about/` | `layouts:panel:nav:/about/` |
| `per_session` | `cart` | `abc123` | `layouts:panel:cart:abc123` |
| `custom` | `price` | `GBP` | `layouts:panel:price:GBP` |

## Render queues and caching

Render queue items (scripts, styles, arbitrary queue items) added by a panel view are stored in the cache **alongside the HTML**. On a cache hit these items are replayed into the current request's queues — so `{% renderscripts %}` and `{% renderstyles %}` still produce correct output.

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    scripts = ScriptQueue()    # must be declared for enqueuing to work

    # nav calls add_script(request, "/js/nav.js") — stored in cache on first hit
    nav = Panel("myapp:nav", cache=cache.sitewide(timeout=3600))
```

Deduplication still applies on replay: the same script or style URL is never emitted twice in a single response.

## Using a different cache backend

All strategy functions accept an optional `backend=` argument naming a key in `settings.CACHES`:

```python
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "redis":   {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://127.0.0.1:6379/1"},
}
```

```python
nav = Panel("myapp:nav", cache=cache.sitewide(timeout=3600, backend="redis"))
```

You can also change the global default backend with `CACHE_BACKEND` in your `DJ_LAYOUTS` settings dict:

```python
# settings.py
DJ_LAYOUTS = {"CACHE_BACKEND": "redis"}
```

## Disabling caching globally

Set `CACHE_ENABLED: False` in `DJ_LAYOUTS` to disable all panel caching regardless of `cache=` arguments:

```python
# settings/local.py
DJ_LAYOUTS = {"CACHE_ENABLED": False}
```

This is useful in development and testing where you want deterministic, uncached rendering.

## `stale_ttl` and `refresh_func`

These arguments are accepted for API stability but are **not yet implemented**. They are silently ignored:

```python
# Accepted, but no stale-while-revalidate behaviour in the current version:
cache.sitewide(timeout=3600, stale_ttl=7200, refresh_func=my_refresh_fn)
```

Do not rely on stale-while-revalidate semantics in the current release.

## Gotchas

### Panel errors are not cached

If a panel raises an exception the error result is **not** written to cache. The panel will be re-executed on the next request, which gives a genuine cache miss (and another chance to succeed).

### Panels that set response headers or cookies

Panel views run on cloned requests and their `HttpResponse` objects are discarded — only the response body is used. If a panel sets cookies or headers via `response.cookies` or `response.headers`, those are silently dropped. Do not rely on panel views to set response-level headers. Use middleware or the main view for that.

### Cache invalidation

dj-layouts does not provide automatic cache invalidation. Use Django's cache API directly to delete entries when your data changes:

```python
from django.core.cache import caches

# Bust the sitewide nav cache:
caches["default"].delete("layouts:panel:nav")

# Bust user 42's account nav:
caches["default"].delete("layouts:panel:account_nav:42")
```

For programmatic invalidation consider wrapping this in a `post_save` signal on the relevant model.

### Per-session panels and session creation

`cache.per_session()` reads `request.session.session_key`. If the session has not been saved yet (e.g. anonymous user with no session data), the key may be `None`. In this case the key component falls back to `"no-session"` and all such requests share one entry.

### Anonymous users with `per_user`

All anonymous users share the `"anonymous"` cache entry. If your anonymous panel output varies by anything other than authentication status — for example, a preferred language stored in a cookie — use `cache.custom()`:

```python
def vary_by_lang(request):
    return request.COOKIES.get("lang", "en")

nav = Panel("myapp:nav", cache=cache.custom(key_func=vary_by_lang, timeout=3600))
```
