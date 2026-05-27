# dj-layouts

[![CI](https://github.com/fukalite/dj-layouts/actions/workflows/ci.yml/badge.svg)](https://github.com/fukalite/dj-layouts/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/dj-layouts?label=PyPI)](https://pypi.org/project/dj-layouts/)
[![Python versions](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)](https://pypi.org/project/dj-layouts/)
[![Django](https://img.shields.io/badge/django-5.2%20%7C%206.0%20%7C%20latest-green)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

A Django layout composition library. Views return their own content as partials; a `Layout` class assembles the full page by calling other views as named panels, concurrently under ASGI.

**[Read the docs →](https://fukalite.github.io/dj-layouts/)**

## Quick start

```bash
pip install dj-layouts
```

```python
# myapp/layouts.py
from dj_layouts import Layout, Panel

class DefaultLayout(Layout):
    template = "layouts/default.html"
    navigation = Panel("core:navigation")
    footer = Panel("<p>© Acme</p>")
```

```python
# myapp/views.py
from dj_layouts import layout

@layout(DefaultLayout)
def homepage(request):
    return render(request, "home/index.html", {"items": get_items()})
```

## HTMX Smart Routing (SPA)

With HTMX Smart Routing, you can turn your standard multi-page Django application into a smooth single-page application (SPA) with zero client-side routing logic.

Opt-in by enabling the setting in your `settings.py`:

```python
DJ_LAYOUTS = {
    "PARTIAL_DETECTORS": ["dj_layouts.detection.htmx_detector"],
    "HTMX_SMART_ROUTING": True,
}
```

Add `hx-boost="true"` to your `<body>`. When a user navigates between views:
- If the next view uses the **same layout**, `dj-layouts` returns only the partial view response and tells HTMX to retarget and swap just the `#panel-content` panel (extremely fast).
- If the next view uses a **different layout**, `dj-layouts` dynamically assembles the new full layout, updates the layout tracker cookie, and tells HTMX to smoothly swap the entire `<body>`.

## Supported versions

| Python | Django    |
| ------ | --------- |
| 3.13   | 5.2 (LTS) |
| 3.14   | 6.0       |
|        | latest    |

## Documentation

Full documentation at **[fukalite.github.io/dj-layouts/](https://fukalite.github.io/dj-layouts/)**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE)
