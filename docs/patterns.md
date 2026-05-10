# Patterns

Common patterns and recipes for dj-layouts.

## Dual-mode views (standalone + panel)

A view decorated with `@layout` is automatically a no-op when called as a panel (`request.layout_role == "panel"`). This means the same view can serve as both the main content view for its own URL and as a panel in another layout — without any extra code.

```python
# myapp/views.py
from dj_layouts import layout, panel_only

@layout("myapp.DefaultLayout")
def article_detail(request, pk):
    """
    When called directly: renders inside DefaultLayout (full page).
    When called as a panel: returns just the article HTML partial.
    """
    article = get_object_or_404(Article, pk=pk)
    return render(request, "myapp/article_detail.html", {"article": article})

# myapp/layouts.py
class HomepageLayout(Layout):
    template = "myapp/homepage.html"
    # Reuse the article_detail view as a "featured article" panel:
    featured = Panel("myapp:article_detail", context={"pk": 1})
```

When `article_detail` is called as a panel, `@layout` detects `layout_role == "panel"` and skips layout wrapping, returning only the `article_detail.html` partial. HTMX requests can also target this URL directly to get the partial without the layout.

---

## Pinning a panel to a specific object

Use `Panel.context` to fix a panel to a specific database object without creating a dedicated URL:

```python
class HomepageLayout(Layout):
    template = "myapp/homepage.html"

    # Always show the staff picks article (pk=42), regardless of the URL
    staff_pick = Panel("myapp:article_detail", context={"pk": 42})
    # Latest announcement (pk determined at class-definition time — use callables for dynamic)
    announcement = Panel("myapp:announcement_detail", context={"pk": 1})
```

!!! warning "Panel.context is config-time data"
    The `context=` dict is evaluated when your `layouts.py` loads — not per-request. Don't use `request.GET` or other runtime data here. For dynamic panel selection, use a callable source.

---

## Dynamic panel selection with a callable

When the panel source depends on the request, use a callable:

```python
def pick_sidebar(request, **ctx):
    if request.user.is_authenticated:
        from myapp.views import user_sidebar
        return user_sidebar(request, **ctx)
    from myapp.views import public_sidebar
    return public_sidebar(request, **ctx)

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    sidebar = Panel(pick_sidebar)
```

The callable receives the panel's cloned request and any `context=` kwargs. It can return an `HttpResponse` or a plain `str`.

---

## Conditional panels (None)

Suppress a panel entirely by setting it to `None`. The template fallback content renders instead:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    ads = Panel(None)      # always suppressed
    sidebar = Panel("myapp:sidebar")

# Per-view: suppress sidebar for the landing page
@layout("myapp.DefaultLayout", panels={"sidebar": None})
def landing(request):
    ...
```

In the layout template:

```html+django
{% panel "ads" %}{# fallback — no ads configured #}{% endpanel %}
{% panel "sidebar" %}<p>No sidebar.</p>{% endpanel %}
```

---

## Static panels (literal HTML)

For completely static panel content, use a literal string source:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    # Literal HTML — no view is called
    cookie_banner = Panel('<div class="cookie-banner">We use cookies.</div>')
    separator = Panel("<hr>")
```

Use `literal=` when the string contains `:` (to avoid URL name auto-detection):

```python
Panel(literal='<a href="https://example.com">Visit us</a>')
```

---

## Combining multiple panels into one slot

Use a list source to compose several panels into a single slot:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    # Render widget_a, then a divider, then widget_b — all in one slot
    widgets = Panel(["myapp:widget_a", "<hr class='divider'>", "myapp:widget_b"])

    # With a join separator
    notifications = Panel(
        ["myapp:system_alerts", "myapp:user_notifications"],
        join="\n"
    )
```

---

## HTMX-ready views

Since every view is already a partial (it returns only its own HTML), dj-layouts views are naturally HTMX-compatible. The `@layout` decorator wraps the full page only when called directly:

```python
@layout("myapp.DefaultLayout")
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    return render(request, "myapp/article_detail.html", {"article": article})
```

HTMX can `hx-get="/articles/5/"` to get just the partial — the `@layout` no-op-when-panel-role behaviour extends to direct HTMX requests too (since `layout_role` is not set on direct requests, HTMX gets the full layout).

For truly partial-only HTMX responses, detect the `HX-Request` header yourself and return an appropriate response:

```python
@layout("myapp.DefaultLayout")
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    if request.headers.get("HX-Request"):
        # Return just the article fragment for HTMX updates
        return render(request, "myapp/article_detail_fragment.html", {"article": article})
    return render(request, "myapp/article_detail.html", {"article": article})
```

!!! note "Partial detection is planned"
    Automatic partial detection (detecting HTMX requests and returning partials without the layout) is a planned feature. For now, detect HTMX headers manually.

---

## Sharing data across panels via layout context

Layout context is the right place for data that multiple panels need:

```python
class DefaultLayout(Layout):
    template = "myapp/layout.html"
    layout_context_defaults = {"site_name": "My App"}

    def get_layout_context(self, request):
        if request.user.is_authenticated:
            return {
                "cart_count": request.user.cart.item_count(),
                "unread_messages": request.user.messages.unread().count(),
            }
        return {}
```

Panel views read the context from `request.layout_context`:

```python
@panel_only
def header(request):
    cart = request.layout_context.get("cart_count", 0)
    msgs = request.layout_context.get("unread_messages", 0)
    return render(request, "myapp/header.html", {"cart": cart, "msgs": msgs})
```

See [Layout Context](layout-context.md) for the full merge order.

---

## Per-view layout context (page title, active nav)

The content view can write to `request.layout_context` to pass page-specific data to the layout template:

```python
@layout("myapp.DefaultLayout")
def products_list(request):
    request.layout_context["page_title"] = "Products"
    request.layout_context["active_nav"] = "products"
    products = Product.objects.all()
    return render(request, "myapp/products.html", {"products": products})
```

The layout template then uses these directly:

```html+django
<title>{{ page_title }} — {{ site_name }}</title>
<nav>
  <a class="{% if active_nav == 'products' %}active{% endif %}" href="/products/">Products</a>
</nav>
```

---

## Pagination within a panel

Panels receive the full cloned request, including query parameters. This means pagination just works:

```python
# URL: /articles/?page=2
# Panel: Panel("myapp:article_list")

@panel_only
def article_list(request):
    page = request.GET.get("page", 1)
    paginator = Paginator(Article.objects.all(), 10)
    return render(request, "myapp/article_list.html", {
        "page_obj": paginator.get_page(page)
    })
```

Since panel requests are cloned from the original request, `request.GET` is available with all query parameters intact.

---

## Panel views that return strings

Panel callables and views can return plain strings instead of `HttpResponse`:

```python
def simple_greeting(request, **ctx):
    return f"<p>Hello, {request.user.first_name}!</p>"

class DefaultLayout(Layout):
    template = "myapp/layout.html"
    greeting = Panel(simple_greeting)
```

---

## Separate layout for unauthenticated users

Use a different layout class for different states:

```python
@layout("myapp.AuthLayout")
def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("/login/")
    return render(request, "myapp/dashboard.html", {})

# Or dynamically:
def dashboard(request):
    layout_name = "myapp.AuthLayout" if request.user.is_authenticated else "myapp.PublicLayout"
    return render_with_layout(request, layout_name, "myapp/dashboard.html")
```
