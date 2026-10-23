"""Página dupla, livro e modo apresentação (A15)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import BOOK, CONTINUOUS, DOUBLE, SINGLE, PdfViewer
from ui.viewer.render import logical_size


def _pdf(path, pages=5):
    c = rl_canvas.Canvas(str(path), pagesize=(300, 400))
    for number in range(pages):
        c.drawString(40, 350, f"pagina {number + 1}")
        c.showPage()
    c.save()
    return str(path)


@pytest.fixture
def viewer(tmp_path):
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    annotation_state = AnnotationState()
    viewer = PdfViewer(session, annotation_state, RedactionState())
    viewer.resize(1000, 700)
    viewer.show()
    session.open(_pdf(tmp_path / "doc.pdf"))
    yield viewer
    viewer.close()


def _settle():
    for _ in range(5):
        QApplication.processEvents()


def test_double_page_and_book_put_two_pages_in_each_row(viewer):
    viewer.set_layout(DOUBLE)
    assert viewer._rows() == [[0, 1], [2, 3], [4]]
    viewer.set_layout(BOOK)
    assert viewer._rows() == [[0], [1, 2], [3, 4]]
    _settle()

    tops = viewer._page_tops
    assert len(viewer._page_labels) == 5
    assert tops[1] == tops[2] and tops[3] == tops[4] and tops[0] < tops[1]
    left, right = viewer._page_labels[1], viewer._page_labels[2]
    container = viewer.scroll_area.widget()
    assert left.mapTo(container, left.rect().topRight()).x() < right.mapTo(container, right.rect().topLeft()).x()
    # A capa do livro fica à direita, onde estaria impressa (as pares ficam à esquerda).
    cover, page_two = viewer._page_labels[0], viewer._page_labels[1]
    assert cover.mapTo(container, cover.rect().topLeft()).x() >= page_two.mapTo(container, page_two.rect().topRight()).x()


def test_next_and_previous_move_a_whole_row(viewer):
    viewer.set_layout(DOUBLE)
    _settle()

    viewer._go_next()
    _settle()
    assert viewer._current_page == 2
    viewer._go_next()
    _settle()
    assert viewer._current_page == 4
    viewer._go_prev()
    _settle()
    assert viewer._current_page == 2


def test_fit_width_fits_both_pages(viewer):
    viewer.set_layout(DOUBLE)
    viewer._fit_width()
    _settle()

    row = viewer._page_labels[0].parentWidget()
    assert row.width() <= viewer.scroll_area.viewport().width()
    assert row.width() > viewer.scroll_area.viewport().width() * 0.9


def test_a_drawing_tool_goes_back_to_single_page(viewer):
    changes = []
    viewer.layout_changed.connect(changes.append)
    viewer.set_layout(BOOK)
    assert viewer.double_page_button.isChecked()

    viewer.annotation_state.set_page_active(True)
    viewer.annotation_state.set_tool("highlight")

    assert viewer.page_layout() == SINGLE and viewer.single_page_button.isChecked()
    assert changes == [BOOK, SINGLE]


def test_view_menu_follows_the_toolbar(tmp_path):
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert not window._presentation_action.isEnabled()
    window.session.open(_pdf(tmp_path / "doc.pdf"))
    assert window._presentation_action.isEnabled()

    window.viewer.continuous_button.click()
    assert window._layout_actions[CONTINUOUS].isChecked()
    window._layout_actions[BOOK].trigger()
    assert window.viewer.page_layout() == BOOK
    window.session.clear()


def test_presentation_shows_one_page_fitted_and_returns_where_it_stopped(viewer):
    window = viewer.start_presentation()
    window.resize(800, 600)
    _settle()

    assert window.isFullScreen() and window.page() == 0
    size = logical_size(window.label.pixmap())
    # Página em pé numa tela mais larga que alta: a altura limita, e a página cabe inteira.
    assert size.height() == window.height() and size.width() <= window.width()

    QTest.keyClick(window, Qt.Key.Key_Space)
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert window.page() == 2
    QTest.keyClick(window, Qt.Key.Key_Left)
    assert window.page() == 1
    QTest.keyClick(window, Qt.Key.Key_End)
    QTest.keyClick(window, Qt.Key.Key_Right)  # não passa da última
    assert window.page() == 4
    QTest.mouseClick(window, Qt.MouseButton.RightButton)
    assert window.page() == 3

    QTest.keyClick(window, Qt.Key.Key_Escape)
    _settle()
    assert viewer._current_page == 3


def test_presentation_does_not_hold_the_working_file(tmp_path):
    from ui.viewer.presentation import PresentationWindow

    QApplication.instance() or QApplication([])
    path = _pdf(tmp_path / "versao.pdf")
    window = PresentationWindow(path, 1)
    window.show()

    os.replace(path, path + ".movido")  # no Windows, falharia com o arquivo aberto

    assert window.page() == 1
    window.close()
