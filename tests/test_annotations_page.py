"""Testes da lista de comentários existentes da aba Anotações (A11)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
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


def _viewer_with(tmp_path, monkeypatch):
    from ui.redaction_state import RedactionState
    from ui.viewer.pdf_viewer import PdfViewer

    page, session, state = _page_with_comments(tmp_path, monkeypatch)
    viewer = PdfViewer(session, state, RedactionState())
    viewer._show_single_page(0)
    state.set_page_active(True)
    return viewer, page, session, state


def test_dragging_draws_a_shape_with_the_chosen_width(tmp_path, monkeypatch):
    viewer, page, _session, state = _viewer_with(tmp_path, monkeypatch)
    page.tool_buttons["arrow"].click()
    page.width_spin.setValue(5)

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_moved(80, 60)
    viewer._on_canvas_released(140, 80)
    viewer._on_canvas_pressed(50, 50)
    viewer._on_canvas_released(51, 50)  # clique sem arrastar: nada

    (spec,) = state.pending()
    assert (spec.kind, spec.width) == ("arrow", 5)
    assert spec.points == [viewer._widget_point_to_pdf(0, 20, 20), viewer._widget_point_to_pdf(0, 140, 80)]


def test_dragging_the_selected_comment_moves_and_resizes_it(tmp_path, monkeypatch):
    viewer, page, session, state = _viewer_with(tmp_path, monkeypatch)
    page.tool_buttons["select"].click()
    _select(page, 1)  # o realce
    before = ListAnnotations().run(session.path())[1].rect
    screen = viewer._user_rect_to_screen(0, before)

    viewer._on_canvas_pressed(screen.center().x(), screen.center().y())
    viewer._on_canvas_moved(screen.center().x() + 30, screen.center().y() + 60)
    viewer._on_canvas_released(screen.center().x() + 30, screen.center().y() + 60)
    wait_for_tasks()

    moved = ListAnnotations().run(session.path())[1]
    scale = viewer._scale
    assert moved.kind == "Highlight"
    assert moved.rect[0] - before[0] == pytest.approx(30 / scale, abs=0.5)
    assert moved.rect[1] - before[1] == pytest.approx(-60 / scale, abs=0.5)  # para baixo na tela
    assert moved.rect[2] - moved.rect[0] == pytest.approx(before[2] - before[0], abs=0.5)

    _select(page, 1)
    screen = viewer._user_rect_to_screen(0, moved.rect)
    corner = screen.bottomRight()
    viewer._on_canvas_pressed(corner.x() - 2, corner.y() - 2)
    viewer._on_canvas_moved(corner.x() + 40, corner.y() - 2)
    viewer._on_canvas_released(corner.x() + 40, corner.y() - 2)
    wait_for_tasks()

    resized = ListAnnotations().run(session.path())[1]
    assert resized.rect[2] - resized.rect[0] == pytest.approx(moved.rect[2] - moved.rect[0] + 42 / scale, abs=0.5)
    session.undo()
    session.undo()
    assert ListAnnotations().run(session.path())[1].rect == before


def test_recolor_and_author_of_new_annotations(tmp_path, monkeypatch):
    from ui.preferences import Preferences

    monkeypatch.setattr("ui.preferences._current", Preferences())  # em memória, só neste teste
    shown = []
    page, session, state = _page_with_comments(tmp_path, monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text, *a: shown.append(text))
    stamp_color = ListAnnotations().run(session.path())[2].color
    page.color_buttons["2196f3"].click()
    _select(page, 0, 1, 2)
    page._recolor_comments()
    wait_for_tasks()

    assert [c.color for c in ListAnnotations().run(session.path())] == ["2196f3", "2196f3", stamp_color]
    assert "Cor trocada em 2 comentário(s)." in shown[-1] and "1 ficou(aram)" in shown[-1]

    page.author_edit.setText("Revisora")
    page.author_edit.editingFinished.emit()
    assert AnnotationsPage(session, state).author_edit.text() == "Revisora"  # fica guardado
