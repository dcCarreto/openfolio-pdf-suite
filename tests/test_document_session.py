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


# -- documento de trabalho (M01) ------------------------------------------------------


def _pdf(path, pages=1):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=200 + index, height=200)
    writer.write(str(path))
    return str(path)


def _apply(session, label, pages=1):
    """Simula uma ferramenta: grava uma versão nova e a abre."""
    session.note_operation(label)
    version = session.new_version_path()
    _pdf(version, pages)
    session.open(version)
    return version


def test_opening_a_file_does_not_copy_it(tmp_path):
    source = _pdf(tmp_path / "contrato.pdf")
    session = DocumentSession()

    session.open(source)

    assert session.path() == source == session.source_path()
    assert not session.is_modified() and not session.can_undo()


def test_an_operation_becomes_an_undoable_step(tmp_path):
    source = _pdf(tmp_path / "contrato.pdf")
    session = DocumentSession()
    session.open(source)

    version = _apply(session, "Marca d'água", pages=2)

    assert session.path() == version and session.source_path() == source
    assert session.is_modified() and session.last_change() == "version"
    assert session.undo_label() == "Marca d'água"
    assert not list(tmp_path.glob("contrato_*"))  # nada intermediário na pasta do usuário

    session.undo()
    assert session.path() == source and not session.is_modified()
    assert session.redo_label() == "Marca d'água"
    session.redo()
    assert session.path() == version


def test_a_new_step_after_undo_drops_the_redo(tmp_path):
    session = DocumentSession()
    session.open(_pdf(tmp_path / "doc.pdf"))
    _apply(session, "Primeira")
    session.undo()

    _apply(session, "Segunda")

    assert not session.can_redo()
    assert session.undo_label() == "Segunda"


def test_save_writes_the_current_version_over_the_users_file(tmp_path):
    from pypdf import PdfReader

    source = _pdf(tmp_path / "doc.pdf")
    session = DocumentSession()
    session.open(source)
    _apply(session, "Inserir", pages=3)

    session.save()

    assert len(PdfReader(source).pages) == 3
    assert not session.is_modified()
    session.undo()
    assert session.is_modified()  # voltou para antes do que foi salvo


def test_save_as_changes_the_documents_file(tmp_path):
    source = _pdf(tmp_path / "doc.pdf")
    session = DocumentSession()
    session.open(source)
    _apply(session, "Comprimir")
    target = str(tmp_path / "copia.pdf")

    session.save_as(target)

    assert session.source_path() == target and not session.is_modified()
    assert (tmp_path / "copia.pdf").exists()


def test_switching_documents_with_unsaved_changes_asks_first(tmp_path):
    session = DocumentSession()
    session.open(_pdf(tmp_path / "a.pdf"))
    _apply(session, "Editar")
    answers = [False]
    session.set_discard_confirmation(lambda: answers.pop(0))

    assert not session.open(_pdf(tmp_path / "b.pdf"))  # cancelado
    assert session.source_path().endswith("a.pdf") and session.is_modified()

    answers.append(True)
    assert session.open(str(tmp_path / "b.pdf"))
    assert session.source_path().endswith("b.pdf") and not session.can_undo()


def test_temporary_versions_are_removed(tmp_path):
    import os

    session = DocumentSession()
    session.open(_pdf(tmp_path / "doc.pdf"))
    version = _apply(session, "Editar")

    session.discard_temporary_files()

    assert not os.path.exists(version)
