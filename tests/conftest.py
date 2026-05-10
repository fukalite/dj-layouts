import pytest


@pytest.fixture()
def locmem_templates(settings):
    """
    Configure in-memory templates for isolation, with the layouts tag library
    available (no need for dj_layouts to be in INSTALLED_APPS for tag discovery).
    """

    def configure(templates_dict: dict) -> None:
        settings.TEMPLATES = [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": False,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                    ],
                    "libraries": {
                        "layouts": "dj_layouts.templatetags.layouts",
                    },
                    "loaders": [
                        ("django.template.loaders.locmem.Loader", templates_dict),
                    ],
                },
            }
        ]

    return configure
