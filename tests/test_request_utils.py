from dj_layouts.context import FrozenLayoutContext, LayoutContext
from dj_layouts.request_utils import clone_request_as_get


def test_clone_forces_get_method(rf):
    request = rf.post("/", data={"foo": "bar"})
    cloned = clone_request_as_get(request)
    assert cloned.method == "GET"


def test_clone_clears_post(rf):
    request = rf.post("/", data={"foo": "bar"})
    cloned = clone_request_as_get(request)
    assert not cloned.POST


def test_clone_clears_files(rf):
    request = rf.post("/", data={}, FILES={})
    cloned = clone_request_as_get(request)
    assert not cloned.FILES


def test_clone_sets_layout_role(rf):
    request = rf.get("/")
    cloned = clone_request_as_get(request)
    assert cloned.layout_role == "panel"


def test_clone_sets_is_layout_partial_false(rf):
    request = rf.get("/")
    cloned = clone_request_as_get(request)
    assert cloned.is_layout_partial is False


def test_clone_sets_frozen_layout_context(rf):
    request = rf.get("/")
    request.layout_context = LayoutContext({"site": "Intranet"})
    cloned = clone_request_as_get(request)
    assert isinstance(cloned.layout_context, FrozenLayoutContext)
    assert cloned.layout_context["site"] == "Intranet"


def test_clone_preserves_path(rf):
    request = rf.get("/some/path/")
    cloned = clone_request_as_get(request)
    assert cloned.path == "/some/path/"


def test_clone_preserves_user(rf):
    from django.contrib.auth.models import AnonymousUser

    request = rf.get("/")
    request.user = AnonymousUser()
    cloned = clone_request_as_get(request)
    assert cloned.user is request.user


def test_clone_is_a_different_object(rf):
    request = rf.get("/")
    cloned = clone_request_as_get(request)
    assert cloned is not request


def test_clone_without_layout_context_sets_empty_frozen(rf):
    request = rf.get("/")
    cloned = clone_request_as_get(request)
    assert isinstance(cloned.layout_context, FrozenLayoutContext)
    assert len(cloned.layout_context) == 0
