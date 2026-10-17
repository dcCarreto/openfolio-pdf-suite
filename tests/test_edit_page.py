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
    state.set_active_page(page if active else None)  # a janela informa a aba visível
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


def test_dragging_in_link_mode_fills_the_link_area(tmp_path):
    viewer, page, state = _setup(tmp_path)
    page.mode_combo.setCurrentIndex(2)  # Adicionar link

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    rect = tuple(spin.value() for spin in (page.link_left_spin, page.link_bottom_spin, page.link_right_spin, page.link_top_spin))
    assert rect[2] > rect[0] and rect[3] > rect[1]
    assert page.edit_text_table.rowCount() == 0  # foi para o link, não para a edição de texto
    assert state.areas() == [(0, rect)]


def test_link_to_remove_is_chosen_from_the_list_or_the_viewer(tmp_path):
    from core.links import AddLink
    from ui.tasks import wait_for_tasks

    viewer, page, state = _setup(tmp_path)
    source = page.session.path()
    linked = tmp_path / "com_links.pdf"
    AddLink().run(source, str(linked), page_number=0, left=10, bottom=10, right=60, top=30, url="https://a.example")
    AddLink().run(str(linked), str(linked), page_number=0, left=200, bottom=200, right=300, top=240, url="https://b.example")
    page.session.open(str(linked))
    page.mode_combo.setCurrentIndex(4)  # Remover link

    page._load_links_to_remove()
    assert wait_for_tasks()
    assert page.remove_links_list.count() == 2
    page.remove_links_list.setCurrentRow(0)
    assert page.remove_link_index_spin.value() == 1

    # Arrastar sobre o segundo link no visualizador o escolhe.
    sx, sy = viewer._geometry(0).user_to_screen(250, 220, viewer._scale)
    viewer._on_canvas_pressed(sx - 5, sy - 5)
    viewer._on_canvas_released(sx + 5, sy + 5)

    assert page.remove_links_list.currentRow() == 1
    assert page.remove_link_index_spin.value() == 2
    assert len(state.areas()) == 2  # os links da página aparecem desenhados


def test_clicking_an_image_in_the_list_chooses_it(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    _viewer, page, _state = _setup(tmp_path)
    item = QListWidgetItem("Página 3 — #2")
    item.setData(Qt.ItemDataRole.UserRole, (2, 1))
    page.images_list.addItem(item)

    page.images_list.setCurrentItem(item)

    assert (page.image_page_spin.value(), page.image_index_spin.value()) == (3, 2)
