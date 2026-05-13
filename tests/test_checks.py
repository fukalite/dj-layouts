from dj_layouts.base import Layout, _registry
from dj_layouts.decorators import _deferred_layout_refs


# ── E001: unresolved string refs ──────────────────────────────────────────────


def test_check_no_errors_when_refs_list_is_empty():
    from dj_layouts.checks import check_layout_string_refs

    assert check_layout_string_refs(app_configs=None) == []


def test_check_no_errors_when_ref_resolves():
    class ValidLayout(Layout):
        template = "layouts/t.html"

    key = next(k for k, v in _registry.items() if v is ValidLayout)
    _deferred_layout_refs.append((key, "some_view"))

    from dj_layouts.checks import check_layout_string_refs

    assert check_layout_string_refs(app_configs=None) == []


def test_check_e001_for_unregistered_string_ref():
    _deferred_layout_refs.append(("nonexistent.Layout", "my_view"))

    from dj_layouts.checks import check_layout_string_refs

    errors = check_layout_string_refs(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == "dj_layouts.E001"
    assert "nonexistent.Layout" in errors[0].msg
    assert "my_view" in errors[0].msg


def test_check_e001_message_lists_registered_layouts():
    class SomeLayout(Layout):
        template = "layouts/t.html"

    _deferred_layout_refs.append(("bad.Ref", "view_fn"))

    from dj_layouts.checks import check_layout_string_refs

    errors = check_layout_string_refs(app_configs=None)
    assert errors[0].id == "dj_layouts.E001"
    # The error message lists what IS registered
    assert "SomeLayout" in errors[0].msg


def test_check_multiple_bad_refs_all_reported():
    _deferred_layout_refs.append(("bad.One", "view_one"))
    _deferred_layout_refs.append(("bad.Two", "view_two"))

    from dj_layouts.checks import check_layout_string_refs

    errors = check_layout_string_refs(app_configs=None)
    ids = [e.id for e in errors]
    assert ids.count("dj_layouts.E001") == 2
    msgs = " ".join(e.msg for e in errors)
    assert "bad.One" in msgs
    assert "bad.Two" in msgs


def test_layout_decorator_with_string_populates_deferred_refs():
    from dj_layouts.decorators import layout

    @layout("missing.SyncLayout")
    def my_view(request):
        pass

    assert any(ref == "missing.SyncLayout" for ref, _ in _deferred_layout_refs)


def test_async_layout_decorator_with_string_populates_deferred_refs():
    from dj_layouts.decorators import async_layout

    @async_layout("missing.AsyncLayout")
    async def my_async_view(request):
        pass

    assert any(ref == "missing.AsyncLayout" for ref, _ in _deferred_layout_refs)


def test_layout_decorator_with_class_does_not_populate_deferred_refs():
    from dj_layouts.decorators import layout

    class InlineLayout(Layout):
        template = "layouts/t.html"

    before = list(_deferred_layout_refs)

    @layout(InlineLayout)
    def my_view(request):
        pass

    assert _deferred_layout_refs == before


def test_async_layout_decorator_with_class_does_not_populate_deferred_refs():
    from dj_layouts.decorators import async_layout

    class InlineLayout(Layout):
        template = "layouts/t.html"

    before = list(_deferred_layout_refs)

    @async_layout(InlineLayout)
    async def my_async_view(request):
        pass

    assert _deferred_layout_refs == before


def test_check_bad_and_good_ref_mixed():
    class GoodLayout(Layout):
        template = "layouts/t.html"

    good_key = next(k for k, v in _registry.items() if v is GoodLayout)
    _deferred_layout_refs.append((good_key, "good_view"))
    _deferred_layout_refs.append(("bad.Layout", "bad_view"))

    from dj_layouts.checks import check_layout_string_refs

    errors = check_layout_string_refs(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == "dj_layouts.E001"
    assert "bad.Layout" in errors[0].msg
