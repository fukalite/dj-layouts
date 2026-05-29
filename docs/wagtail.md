# Wagtail Integration

`dj-layouts` provides out-of-the-box integration with Wagtail CMS through the `WagtailLayoutMixin`. This mixin allows Wagtail Page models to seamlessly participate in layout compositions, concurrent rendering, and HTMX Smart Routing transitions.

---

## Quick Start

To use the mixin, import and inherit from `WagtailLayoutMixin` in your Wagtail `Page` model class.

> [!IMPORTANT]
> The mixin **MUST** be placed before the Wagtail `Page` class in the Python Method Resolution Order (MRO) to correctly override Wagtail's serving lifecycle.

```python
# myapp/models.py
from wagtail.models import Page
from dj_layouts.wagtail import WagtailLayoutMixin

class BlogPage(WagtailLayoutMixin, Page):
    layout_class = "blog.BlogLayout"
    template = "blog/blog_page.html"
```

In your page template (`blog_page.html`), author only the page's raw partial contents (no structural layout wraps):

```html
<!-- blog/blog_page.html -->
<h1>{{ page.title }}</h1>
<div class="intro">{{ page.intro }}</div>
<div class="body">
  {{ page.body }}
</div>
```

---

## Dynamic Template Inheritance (Dual Rendering)

In a standard Wagtail configuration, page templates statically inherit from a root document (e.g. `{% extends "base.html" %}`). If you are gradually transitioning an existing Wagtail codebase or want your pages to be rendered cleanly both **inside** and **outside** of the `dj-layouts` wrapper, you should use **Dynamic Template Inheritance**.

### The Problem with Static Inheritance
If `blog_page.html` statically inherits from `base.html`, then:
- **Full Page Loads:** `render_with_layout()` renders `blog_page.html`, which pulls in the full `base.html` shell. It then wraps that full HTML document inside the resolved `Layout` template, resulting in nested duplicate `<html>`, `<head>`, and `<body>` tags.
- **Partial Page Loads (HTMX):** `serve()` returns `super().serve()`, which renders the whole `base.html` shell, returning a full HTML document instead of just the partial content.

### The Solution
`WagtailLayoutMixin` dynamically injects `"base_template": "layouts/blank.html"` into the template context on both partial and full page rendering paths.

#### 1. Setup the Template Inheritance
Configure your page template to inherit dynamically from `base_template`, defaulting to `base.html` if it is served outside of `dj-layouts`:

```html
<!-- blog/blog_page.html -->
{% extends base_template|default:"base.html" %}

{% block content %}
  <h1>{{ page.title }}</h1>
  <div class="intro">{{ page.intro }}</div>
  <div class="body">
    {{ page.body }}
  </div>
{% endblock %}
```

When rendered under `dj-layouts` (either during full assembly or partial HTMX swaps), the page template will automatically inherit from `layouts/blank.html`, rendering only the content block cleanly. If Wagtail serves the page directly (e.g. during preview mode or if the mixin is bypassed), it defaults to `base.html`, ensuring all structural wraps are preserved.

---

## Core Mixin Behaviours

### Preview Mode Bypass
If `request.is_preview` is `True` (such as when a content editor is previewing a page inside Wagtail's admin panel), `WagtailLayoutMixin` skips the layout system entirely and defaults back to standard Wagtail rendering. This ensures preview frames render properly in the admin interface.

### Dotted String Layout Resolution
Like `LayoutMixin`, the `layout_class` attribute supports both a direct `Layout` subclass reference and a dotted string representation resolved at runtime (e.g., `"myapp.BlogLayout"`).

### Panel Overrides
You can supply per-page panel overrides using the `layout_panels` class attribute:

```python
from dj_layouts.panels import Panel

class BlogPage(WagtailLayoutMixin, Page):
    layout_class = "blog.BlogLayout"
    layout_panels = {
        "sidebar": Panel("blog:widgets")
    }
```
