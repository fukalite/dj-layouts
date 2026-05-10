from __future__ import annotations

import traceback
from dataclasses import dataclass


@dataclass
class PanelError:
    """Data carrier for a panel rendering failure. Not an exception itself."""

    panel_name: str
    source: object
    exception: BaseException
    traceback_str: str

    @classmethod
    def from_exc(
        cls, panel_name: str, source: object, exc: BaseException
    ) -> PanelError:
        return cls(
            panel_name=panel_name,
            source=source,
            exception=exc,
            traceback_str=traceback.format_exc(),
        )


class PanelRenderError(Exception):
    """Raised in DEBUG mode when a panel fails, so Django's error page is shown."""

    def __init__(self, panel_error: PanelError) -> None:
        self.panel_error = panel_error
        super().__init__(
            f"Panel '{panel_error.panel_name}' failed: {panel_error.exception!r}"
        )
