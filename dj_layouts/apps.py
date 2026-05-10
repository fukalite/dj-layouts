from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class DjLayoutsConfig(AppConfig):
    name = "dj_layouts"
    verbose_name = "Layouts"

    def ready(self) -> None:
        autodiscover_modules("layouts")
        from dj_layouts import (
            checks,  # noqa: F401 — registers system checks via @register()
        )
