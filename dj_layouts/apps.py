from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class DjLayoutsConfig(AppConfig):
    name = "dj_layouts"
    verbose_name = "Layouts"

    def ready(self) -> None:
        autodiscover_modules("layouts")
