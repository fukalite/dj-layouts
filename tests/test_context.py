import pytest

from dj_layouts.context import FrozenLayoutContext, LayoutContext


def test_layout_context_is_a_dict():
    ctx = LayoutContext({"foo": "bar"})
    assert ctx["foo"] == "bar"


def test_layout_context_is_mutable():
    ctx = LayoutContext()
    ctx["key"] = "value"
    assert ctx["key"] == "value"
    ctx.update({"a": 1})
    del ctx["a"]


def test_frozen_layout_context_reads_work():
    ctx = FrozenLayoutContext({"foo": "bar"})
    assert ctx["foo"] == "bar"
    assert len(ctx) == 1


def test_frozen_layout_context_setitem_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx["x"] = 2


def test_frozen_layout_context_delitem_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        del ctx["x"]


def test_frozen_layout_context_update_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx.update({"y": 2})


def test_frozen_layout_context_pop_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx.pop("x")


def test_frozen_layout_context_clear_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx.clear()


def test_frozen_layout_context_setdefault_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx.setdefault("y", 2)


def test_frozen_layout_context_popitem_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx.popitem()


def test_frozen_layout_context_ior_raises():
    ctx = FrozenLayoutContext({"x": 1})
    with pytest.raises(TypeError, match="read-only"):
        ctx |= {"y": 2}


def test_layout_context_can_be_frozen():
    ctx = LayoutContext({"a": 1, "b": 2})
    frozen = FrozenLayoutContext(ctx)
    assert frozen["a"] == 1
    assert frozen["b"] == 2
