"""Testes da lista de comentários existentes da aba Anotações (A11)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.annotations import AddAnnotations, AnnotationSpec, ListAnnotations
from core.xfdf import ExportAnnotationsXFDF
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.pages.annotations_page import AnnotationsPage, format_pdf_date
from ui.tasks import wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_pdf(path) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 400))
    canvas.drawString(40, 340, "texto")
    canvas.showPage()
    canvas.save()


def _page_with_comments(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    plain, annotated = tmp_path / "doc.pdf", tmp_path / "anotado.pdf"
    _make_pdf(plain)
    specs = [
        AnnotationSpec(page_index=0, kind="note", position=(300, 300), text="Primeira"),
        AnnotationSpec(page_index=0, kind="highlight", quads=[(40, 335, 90, 352)]),
        AnnotationSpec(page_index=0, kind="stamp", position=(100, 100), text="APROVADO"),
    ]
    AddAnnotations().run(str(plain), str(annotated), specs, author="Ana")
    session = DocumentSession()
    session.open(str(annotated))
    state = AnnotationState()
    return AnnotationsPage(session, state), session, state


def _select(page, *rows):
    page.comments_list.clearSelection()
    for row in rows:
        page.comments_list.item(row).setSelected(True)


def test_comments_are_listed_and_selecting_one_shows_it(tmp_path, monkeypatch):
    page, _session, state = _page_with_comments(tmp_path, monkeypatch)

    assert page.comments_list.count() == 3
    assert page.comments_list.item(0).text().startswith("Página 1 · Nota · Ana")
    _select(page, 0)
    assert page.comment_text_edit.toPlainText() == "Primeira"
    assert state.selected_comment()[0] == 0
    # O texto do carimbo é desenho: não dá para editar pela lista.
    _select(page, 2)
    assert page.comment_text_edit.isReadOnly()
    _select(page, 0, 1)
    assert not page.update_comment_button.isEnabled() and page.remove_comments_button.isEnabled()
    assert state.selected_comment() is None


def test_editing_and_removing_create_versions_that_undo_reverts(tmp_path, monkeypatch):
    page, session, _state = _page_with_comments(tmp_path, monkeypatch)

    _select(page, 0)
    page.comment_text_edit.setPlainText("Corrigida")
    page.comment_author_edit.setText("Bia")
    page._update_comment()
    wait_for_tasks()
    first = ListAnnotations().run(session.path())[0]
    assert (first.content, first.author) == ("Corrigida", "Bia")
    assert page.comment_text_edit.toPlainText() == "Corrigida"  # a seleção volta depois de recarregar

    _select(page, 0, 1)
    page._remove_comments()
    wait_for_tasks()
    assert [c.kind for c in ListAnnotations().run(session.path())] == ["FreeText"]
    assert page.comments_list.count() == 1

    session.undo()
    assert page.comments_list.count() == 3


def test_importing_xfdf_adds_the_comments_to_the_open_document(tmp_path, monkeypatch):
    page, session, _state = _page_with_comments(tmp_path, monkeypatch)
    xfdf = tmp_path / "revisao.xfdf"
    ExportAnnotationsXFDF().run(session.path(), str(xfdf))
    blank = tmp_path / "branco.pdf"
    _make_pdf(blank)
    session.open(str(blank))
    assert page.comments_list.count() == 1  # "Nenhum comentário no documento."
    assert not page.comments_list.item(0).isSelected()

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(xfdf), ""))
    page._import_xfdf()
    wait_for_tasks()

    assert [c.kind for c in ListAnnotations().run(session.path())] == ["Text", "Highlight", "FreeText"]
    assert page.comments_list.count() == 3
    assert session.can_undo()


def test_format_pdf_date():
    assert format_pdf_date("D:20261019143005-03'00'") == "19/10/2026 14:30"
    assert format_pdf_date("D:20261019") == "19/10/2026"
    assert format_pdf_date("ontem") == ""
