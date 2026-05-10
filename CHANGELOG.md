# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - unreleased

### Added

- `Layout` base class with `__init_subclass__` auto-registration
- `Panel` descriptor with string/callable/list source resolution
- String source auto-detection: `":"` in string → `reverse()`, otherwise literal HTML
- `Panel(url_name=...)` and `Panel(literal=...)` explicit escape hatches
- `@layout` decorator — wraps a sync view to render inside a Layout
- `render_with_layout` — functional equivalent of `@layout` for sync views
- `@async_layout` decorator — wraps an async view; panels run concurrently via `asyncio.gather`
- `async_render_with_layout` — functional equivalent of `@async_layout` for async views
- `@panel_only` decorator — restricts a view to panel-role requests only
- `resolve_panel_source` / `async_resolve_panel_source` — public panel resolution API
- `LayoutContext` / `FrozenLayoutContext` — mutable context for main view, frozen for panels
- Error handling: `on_panel_error` hook, `LAYOUTS_DEBUG_ERRORS` setting
- `{% panel %}` / `{% endpanel %}` template tags
- Panel request cloning — panels receive a GET clone with `layout_role="panel"`
- List panel sources — multiple sources joined into a single panel
