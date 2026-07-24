"""Testes do estado compartilhado da ferramenta de anotações (ui/annotation_state.py)."""

import pytest

from core.annotations import AnnotationSpec
from ui.annotation_state import DEFAULT_COLOR, AnnotationState


def test_starts_with_no_tool_and_default_color():
    state = AnnotationState()
    assert state.active_tool() is None
    assert state.active_color() == DEFAULT_COLOR
    assert state.pending() == []
    assert state.is_page_active() is False


def test_set_tool_emits_signal_only_on_change():
    state = AnnotationState()
    calls = []
    state.tool_changed.connect(lambda: calls.append(1))

    state.set_tool("highlight")
    assert state.active_tool() == "highlight"
    assert len(calls) == 1

    state.set_tool("highlight")
    assert len(calls) == 1


def test_set_tool_rejects_invalid_value():
    state = AnnotationState()
    with pytest.raises(ValueError):
        state.set_tool("not-a-real-tool")


def test_set_page_active_emits_tool_changed():
    state = AnnotationState()
    calls = []
    state.tool_changed.connect(lambda: calls.append(1))

    state.set_page_active(True)
    assert state.is_page_active() is True
    assert len(calls) == 1

    state.set_page_active(True)  # já ativo: não deve emitir de novo
    assert len(calls) == 1


def test_pending_add_remove_clear():
    state = AnnotationState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))

    spec = AnnotationSpec(page_index=0, kind="highlight", quads=[(0, 0, 10, 10)])
    state.add_pending(spec)
    assert state.pending() == [spec]
    assert len(calls) == 1

    state.remove_pending(spec)
    assert state.pending() == []
    assert len(calls) == 2

    state.add_pending(spec)
    state.clear_pending()
    assert state.pending() == []
    assert len(calls) == 4


def test_clear_pending_is_a_noop_when_already_empty():
    state = AnnotationState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))

    state.clear_pending()

    assert calls == []


def test_pending_returns_a_copy_not_the_internal_list():
    state = AnnotationState()
    spec = AnnotationSpec(page_index=0, kind="highlight", quads=[(0, 0, 10, 10)])
    state.add_pending(spec)

    snapshot = state.pending()
    snapshot.append(AnnotationSpec(page_index=1, kind="note", position=(0, 0), text="x"))

    assert len(state.pending()) == 1
