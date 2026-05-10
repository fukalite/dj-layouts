from dj_layouts.errors import PanelError, PanelRenderError


def test_panel_error_is_dataclass():
    err = PanelError(
        panel_name="navigation",
        source="core:navigation",
        exception=ValueError("boom"),
        traceback_str="Traceback...",
    )
    assert err.panel_name == "navigation"
    assert err.source == "core:navigation"
    assert isinstance(err.exception, ValueError)
    assert err.traceback_str == "Traceback..."


def test_panel_error_is_not_an_exception():
    err = PanelError("nav", "core:nav", ValueError(), "tb")
    assert not isinstance(err, Exception)


def test_panel_render_error_is_exception():
    panel_error = PanelError("nav", "core:nav", ValueError("x"), "tb")
    exc = PanelRenderError(panel_error)
    assert isinstance(exc, Exception)
    assert exc.panel_error is panel_error


def test_panel_render_error_str_includes_panel_name():
    panel_error = PanelError("navigation", "core:nav", ValueError("x"), "tb")
    exc = PanelRenderError(panel_error)
    assert "navigation" in str(exc)
