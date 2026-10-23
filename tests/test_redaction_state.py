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


def test_add_pending_ignores_duplicates():
    state = RedactionState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))

    assert state.add_pending(RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)) is True
    assert state.add_pending(RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)) is False

    assert len(state.pending()) == 1
    assert len(calls) == 1


def test_add_many_adds_only_new_rects_with_a_single_signal():
    state = RedactionState()
    calls = []
    state.pending_changed.connect(lambda: calls.append(1))
    a = RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10, kind="cpf", text="1")
    b = RedactionRect(page_index=1, left=0, bottom=0, right=10, top=10, kind="cpf", text="2")

    assert state.add_many([a, b, a]) == 2
    assert state.add_many([a]) == 0  # rodar a detecção de novo não duplica a lista

    assert state.pending() == [a, b]
    assert len(calls) == 1


def test_selection_follows_the_pending_list():
    state = RedactionState()
    a = RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)
    b = RedactionRect(page_index=1, left=0, bottom=0, right=10, top=10)
    state.add_many([a, b])
    selections = []
    state.selection_changed.connect(lambda: selections.append(state.selected()))

    state.set_selected(b)
    assert state.selected() == b

    state.remove_many([b])  # remover a área selecionada desfaz a seleção
    assert state.pending() == [a]
    assert state.selected() is None
    assert selections == [b, None]


def test_set_selected_ignores_rects_that_are_not_pending():
    state = RedactionState()
    calls = []
    state.selection_changed.connect(lambda: calls.append(1))

    state.set_selected(RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10))

    assert state.selected() is None
    assert calls == []


def test_clear_pending_clears_the_selection():
    state = RedactionState()
    rect = RedactionRect(page_index=0, left=0, bottom=0, right=10, top=10)
    state.add_pending(rect)
    state.set_selected(rect)

    state.clear_pending()

    assert state.selected() is None
