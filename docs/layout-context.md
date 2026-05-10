# Layout Context

Layout context is a shared dictionary that flows from the Layout class to the content view and is readable (but not writable) by panel views. Use it for data that belongs to the page as a whole — page title, active navigation item, current user's display name, etc.

## The three merge levels

Layout context is assembled in three stages. **Later stages win** over earlier ones:

| Stage | Source | Priority |
|---|---|---|
| 1 | `layout_context_defaults` (class attribute) | Lowest |
| 2 | `get_layout_context(request)` (method) | Middle |
| 3 | `request.layout_context[key] = val` in the content view | Highest |

A key set in stage 3 overrides the same key from stages 1 and 2.

### Stage 1 — `layout_context_defaults`

Static defaults defined as a class attribute:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {
        "site_name": "My App",
        "theme": "light",
    }
```

### Stage 2 — `get_layout_context(request)`

Dynamic context computed per-request. Override this method to add request-dependent data:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {"site_name": "My App"}

    def get_layout_context(self, request):
        return {
            "current_user": request.user,
            "is_authenticated": request.user.is_authenticated,
        }
```

This method is called **before** your content view runs, so the content view can rely on these values already being present in `request.layout_context`.

### Stage 3 — Content view writes

Your content view can add or override individual keys by writing to `request.layout_context`:

```python
@layout("myapp.DefaultLayout")
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    request.layout_context["page_title"] = product.name
    request.layout_context["active_nav"] = "products"
    return render(request, "myapp/product_detail.html", {"product": product})
```

!!! tip "Set page-level context in the view, not the layout"
    Things that vary per-page (page title, active navigation item) belong in stage 3 writes. Things that are always the same (site name) belong in `layout_context_defaults`. Things that depend on the request but not the specific page (current user) belong in `get_layout_context()`.

## `LayoutContext` — main view (read/write)

`request.layout_context` in the main (content) view is a `LayoutContext` instance. It behaves like a regular Python dict:

```python
@layout("myapp.DefaultLayout")
def my_view(request):
    # Read
    site = request.layout_context["site_name"]
    theme = request.layout_context.get("theme", "light")

    # Write
    request.layout_context["page_title"] = "My Page"

    # Update multiple keys at once
    request.layout_context.update({"active_nav": "home", "show_breadcrumbs": True})

    return HttpResponse(...)
```

`LayoutContext` is a plain `dict` subclass — all dict methods work.

## `FrozenLayoutContext` — panel views (read-only)

`request.layout_context` in panel views is a `FrozenLayoutContext` — a read-only snapshot of the context at the time the layout engine clones the request.

Reading works exactly like a dict:

```python
@panel_only
def sidebar(request):
    active = request.layout_context.get("active_nav", "home")
    return render(request, "myapp/sidebar.html", {"active": active})
```

**Writing raises `TypeError`:**

```python
@panel_only
def bad_panel(request):
    request.layout_context["key"] = "value"  # TypeError: layout_context is read-only in panel views
```

This is intentional. Panels are independent — they read shared context but cannot influence each other via the layout context.

!!! warning "Writes from panel views are silently ignored — actually, they raise"
    Don't try to write to `request.layout_context` in a panel view. It raises `TypeError`, not a silent no-op. If you need the panel to communicate data to another panel, use a different mechanism (e.g. database, cache, or have the layout's `get_layout_context()` fetch shared data).

## Using context in the layout template

All layout context variables are available **directly** in the layout template — they are merged into the template context dict:

```html+django
{# myapp/layout.html #}
{% load layouts %}
<!doctype html>
<html>
<head>
  <title>{{ page_title|default:site_name }}</title>
</head>
<body>
  <nav>
    <a class="{% if active_nav == 'home' %}active{% endif %}" href="/">Home</a>
  </nav>
  {% panel "content" %}{% endpanel %}
</body>
</html>
```

`page_title`, `site_name`, and `active_nav` come from the layout context. You don't need to pass them explicitly to the template — the layout engine merges them automatically.

`request` is also available in the layout template directly.

## Accessing layout context in panel templates

Panel views receive a frozen copy of the layout context on `request.layout_context`. Pass it to the template as needed:

```python
@panel_only
def sidebar(request):
    ctx = {
        "active_nav": request.layout_context.get("active_nav"),
        "user": request.user,
    }
    return render(request, "myapp/sidebar.html", ctx)
```

## When is `request.layout_context` set?

`request.layout_context` is set **before** your content view is called. This means:

- The content view can read `request.layout_context` from the very first line
- Templates rendered by the content view can access `request.layout_context` via the request
- The content view can also write new values that will appear in the layout template

```python
@layout("myapp.DefaultLayout")
def my_view(request):
    # request.layout_context is already populated here
    assert "site_name" in request.layout_context  # from layout_context_defaults
    request.layout_context["page_title"] = "Hello"  # will appear in layout template
    return HttpResponse(...)
```

## Full example

```python
# myapp/layouts.py
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {
        "site_name": "My App",
        "support_email": "help@example.com",
    }

    def get_layout_context(self, request):
        return {
            "user": request.user,
            "notifications_count": (
                request.user.notifications.unread().count()
                if request.user.is_authenticated else 0
            ),
        }

# myapp/views.py
@layout("myapp.DefaultLayout")
def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug)
    request.layout_context["page_title"] = article.title
    request.layout_context["active_nav"] = "blog"
    return render(request, "myapp/article_detail.html", {"article": article})
```

In the layout template, you now have `site_name`, `support_email`, `user`, `notifications_count`, `page_title`, and `active_nav` all available as top-level template variables.
