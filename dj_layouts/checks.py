from django.core.checks import Error, register


@register()
def check_layout_string_refs(app_configs, **kwargs):
    """
    E001: A string ref passed to @layout or @async_layout does not match any
    registered Layout. All refs are collected at decoration time; by AppConfig.ready()
    every Layout subclass should already be in the registry via __init_subclass__.
    """
    from dj_layouts.base import _registry
    from dj_layouts.decorators import _deferred_layout_refs

    errors = []
    for ref, view_name in _deferred_layout_refs:
        if ref not in _registry:
            errors.append(
                Error(
                    f"@layout string ref {ref!r} (used on view {view_name!r}) "
                    f"is not registered. "
                    f"Did you forget to import the Layout class or add its app to INSTALLED_APPS? "
                    f"Registered layouts: {sorted(_registry)}",
                    id="dj_layouts.E001",
                )
            )
    return errors
