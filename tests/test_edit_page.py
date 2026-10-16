"""Aba Editar, modo "Editar texto": marcar a área arrastando no visualizador (B25)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from ui.annotation_state import AnnotationState
from ui.area_pick_state import AreaPickState
from ui.document_session import DocumentSession
from ui.pages.edit_page import EditPage
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_pdf(path) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    c.drawString(40, 250, "Valor antigo")
    c.showPage()
    c.save()


def _setup(tmp_path, active=True):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    session = DocumentSession()
    state = AreaPickState()
    viewer = PdfViewer(session, AnnotationState(), RedactionState(), area_pick_state=state)
    page = EditPage(session, state)
    session.open(str(path))
    state.set_page_active(active)
    page.mode_combo.setCurrentIndex(1)  # Editar texto
    return viewer, page, state


def test_dragging_in_the_viewer_adds_an_area_row(tmp_path):
    viewer, page, state = _setup(tmp_path)

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    table = page.edit_text_table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "1"
    left, bottom, right, top = (float(table.item(0, column).text()) for column in range(1, 5))
    assert right > left and top > bottom
    assert state.areas() == [(0, (left, bottom, right, top))]  # o visualizador desenha a área


def test_text_typed_in_the_editor_goes_to_the_selected_area(tmp_path):
    viewer, page, _state = _setup(tmp_path)
    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    page.edit_text_editor.setPlainText("Linha 1\nLinha 2")

    assert page.edit_text_table.item(0, 5).text() == "Linha 1\nLinha 2"


def test_viewer_does_not_pick_areas_in_other_modes(tmp_path):
    viewer, page, state = _setup(tmp_path)
    page.mode_combo.setCurrentIndex(0)  # Substituir imagem

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    assert not state.is_page_active()
    assert page.edit_text_table.rowCount() == 0


def test_viewer_does_not_pick_areas_when_the_edit_tab_is_hidden(tmp_path):
    viewer, page, state = _setup(tmp_path, active=False)

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    assert page.edit_text_table.rowCount() == 0
