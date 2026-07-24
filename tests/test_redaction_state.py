"""Testes do estado compartilhado da ferramenta de redação (ui/redaction_state.py)."""

from core.redaction import RedactionRect
from ui.redaction_state import RedactionState


def test_starts_inactive_with_no_pending():
    state = RedactionState()
    assert state.is_page_active() is False
    assert state.pending() == []


def test_set_page_active_emits_signal_only_on_change():
    state = RedactionState()
    calls = []
    state.active_changed.connect(lambda: calls.append(1))

    state.set_page_active(True)
    assert state.is_page_active() is True
    assert len(calls) == 1

    state.set_page_active(True)
    assert len(calls) == 1

    state.set_page_active(False)
    assert len(calls) == 2


def test_pending_add_remove_clear():
    state = RedactionState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))

    rect = RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)
    state.add_pending(rect)
    assert state.pending() == [rect]
    assert len(calls) == 1

    state.remove_pending(rect)
    assert state.pending() == []
    assert len(calls) == 2

    state.add_pending(rect)
    state.clear_pending()
    assert state.pending() == []
    assert len(calls) == 4


def test_clear_pending_is_a_noop_when_already_empty():
    state = RedactionState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))

    state.clear_pending()

    assert calls == []


def test_pending_returns_a_copy_not_the_internal_list():
    state = RedactionState()
    rect = RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)
    state.add_pending(rect)

    snapshot = state.pending()
    snapshot.append(RedactionRect(page_index=1, left=0, bottom=0, right=5, top=5))

    assert len(state.pending()) == 1
