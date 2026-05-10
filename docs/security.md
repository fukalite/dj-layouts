# Security

Key security considerations when using dj-layouts.

## `@panel_only` — preventing direct access

Use `@panel_only` on any view that should only be called as a panel. It returns **403 Forbidden** when the view is called directly (i.e. without `request.layout_role == "panel"`):

```python
from dj_layouts import panel_only

@panel_only
def sidebar(request):
    return render(request, "myapp/sidebar.html", {})
```

Direct browser access to the sidebar URL returns 403. Panel views called via the Layout engine return their HTML normally.

!!! warning "Panel URLs are still publicly routable"
    Even with `@panel_only`, the URL is still reachable. Anyone can craft a request that sets `layout_role = "panel"` — this is a request attribute, not a header, so it can only be set server-side. A direct HTTP request will never have `layout_role` set, so `@panel_only` reliably returns 403 for direct requests.

    However, if you need the panel content to be truly private (only renderable by the layout engine), you should also add your own authentication check inside the panel view.

## Panels are public endpoints — add your own auth

Panels are called as regular Django views. They have their own URLs and are subject to the same access control requirements as any other view. **A panel view is only as protected as the checks inside it.**

If your panel displays user-specific data, check authentication yourself:

```python
@panel_only
def user_profile_panel(request):
    if not request.user.is_authenticated:
        return HttpResponse("")  # empty — let template fallback render
    return render(request, "myapp/profile_panel.html", {"user": request.user})
```

Do not assume that because a view is only called as a panel, it can't be accessed directly or by other means.

## Panels receive GET-only requests

Panel views always receive a **cloned, GET-only** request:

- `request.method` is always `"GET"`
- `request.POST` is empty
- `request.FILES` is empty

This means panel views **cannot process form submissions**, **cannot mutate state via POST**, and **cannot read file uploads**. This is a security feature — it prevents panels from accidentally acting on POST data that arrived with the original request.

If a panel needs to show form-related state, read it from the database, not from `request.POST`.

## No middleware on panel requests

Panels do **not** go through the Django middleware stack. The request is cloned from the original request (which did go through middleware), but the panel view is called directly — bypassing all middleware.

This means:

| Middleware behaviour | Effect on panels |
|---|---|
| Session middleware | Session is available (carried from original request) |
| Auth middleware | `request.user` is available (from original request) |
| Security headers middleware | Headers not set on panel response (panel response is not the final response) |
| CSRF middleware | CSRF token not checked (panel request is GET, not POST) |
| Custom middleware that sets `request.X` | `request.X` is available (carried via request copy) |
| Custom middleware that modifies the response | Does not run; panel response is consumed by the layout engine |

**The key implication:** If you rely on middleware to enforce authentication (e.g. `LoginRequiredMiddleware`), that middleware will **not** run for panel views. You must check `request.user.is_authenticated` inside your panel views.

!!! warning "Auth middleware does not protect panel views"
    If you use `LoginRequiredMiddleware` or a similar middleware-based auth gate, panel views bypass it. Always add authentication checks directly in panel views that return sensitive data.

## Panel context is configuration-time only

`Panel.context` kwargs are fixed at class-definition time (when `layouts.py` loads). They cannot contain runtime or request-time values. This is enforced by Python's class definition model — there is no `request` object available when panels are declared.

This is intentional. Do not try to work around it:

```python
# WRONG — this doesn't work anyway, but illustrates the point:
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    # Panel.context cannot reference request — it's evaluated at import time
    user_panel = Panel("myapp:user_info", context={"user_id": request.user.id})  # NameError
```

For request-dependent panel behaviour, use:

- A **callable** panel source that reads from `request` directly
- **`get_layout_context()`** to make request-time data available via `request.layout_context`
- The **panel view itself** to fetch data from the database

## Literal panel sources

Strings passed as `Panel(literal="...")` are returned as raw HTML without escaping. Do not construct literal panel strings from user-supplied input:

```python
# DANGEROUS — don't do this:
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    banner = Panel(literal=f"<p>Hello {user_name}</p>")  # XSS if user_name is untrusted
```

Literal sources are for truly static, developer-controlled HTML. For dynamic content, use a view.

## Template tag safety

The `{% panel %}` template tag inserts panel HTML with `{% autoescape off %}` semantics — panel output is rendered as raw HTML. This is intentional (panels produce HTML), but means you should not allow untrusted content to reach a panel source.

If a panel calls an external service or processes user data, make sure the panel view properly sanitises or escapes its output.

## Summary

| Threat | Mitigation |
|---|---|
| Direct access to panel URLs | `@panel_only` returns 403 |
| Panel accessing sensitive data without auth | Add auth check inside panel view |
| Panel mutating state via POST | Panel requests are always GET |
| Middleware auth bypass for panels | Add auth checks inside panel views directly |
| XSS via literal panel content | Never use user-supplied data in `Panel(literal=...)` |
| XSS via panel view output | Sanitise output in the panel view |
