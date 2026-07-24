"""Testes da sessão de documento compartilhada (ui/document_session.py)."""

from ui.document_session import DocumentSession


def test_starts_with_no_path():
    session = DocumentSession()
    assert session.path() is None


def test_open_sets_path_and_emits_signal():
    session = DocumentSession()
    calls = []
    session.path_changed.connect(lambda: calls.append(1))

    session.open("C:/some/file.pdf")

    assert session.path() == "C:/some/file.pdf"
    assert len(calls) == 1


def test_open_again_emits_signal_even_with_same_path():
    session = DocumentSession()
    session.open("C:/some/file.pdf")
    calls = []
    session.path_changed.connect(lambda: calls.append(1))

    session.open("C:/some/file.pdf")

    assert len(calls) == 1


def test_clear_resets_path_and_emits_signal():
    session = DocumentSession()
    session.open("C:/some/file.pdf")
    calls = []
    session.path_changed.connect(lambda: calls.append(1))

    session.clear()

    assert session.path() is None
    assert len(calls) == 1
