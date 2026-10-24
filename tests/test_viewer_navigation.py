"""Visualizador (M09, M10): teclado, Ctrl+roda, ir para página, ajustar, girar e busca."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QInputDialog
from reportlab.pdfgen import canvas as rl_canvas

from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer


def _pdf(path, pages=4, size=(400, 300), text="palavra"):
    c = rl_canvas.Canvas(str(path), pagesize=size)
    for number in range(pages):
        c.drawString(40, 250, f"{text} {text} pagina {number + 1}")
        c.showPage()
    c.save()
    return str(path)


@pytest.fixture
def viewer(tmp_path):
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.resize(900, 700)
    session.open(_pdf(tmp_path / "doc.pdf"))
    return viewer


def _wheel(viewer, delta, modifiers):
    return QWheelEvent(
        QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_ctrl_wheel_zooms_instead_of_scrolling(viewer):
    before = viewer._scale

    handled = viewer.eventFilter(viewer.scroll_area.viewport(), _wheel(viewer, 120, Qt.KeyboardModifier.ControlModifier))

    assert handled and viewer._scale > before
    assert not viewer.eventFilter(viewer.scroll_area.viewport(), _wheel(viewer, 120, Qt.KeyboardModifier.NoModifier))


def test_keyboard_navigation_handlers(viewer):
    viewer._go_last()
    assert viewer._current_page == 3
    viewer._go_prev()
    assert viewer._current_page == 2
    viewer._go_first()
    assert viewer._current_page == 0


def test_go_to_page_asks_for_the_number(viewer, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getInt", lambda *args, **kwargs: (3, True))

    viewer._ask_go_to_page()  # Ctrl+G

    assert viewer._current_page == 2


def test_typing_a_page_number_in_the_bar_goes_to_it(viewer):
    assert viewer.page_field.text() == "1" and viewer.page_total.text() == "de 4"

    viewer.page_field.setText("3")
    viewer.page_field.returnPressed.emit()
    assert viewer._current_page == 2 and viewer.page_field.text() == "3"

    viewer.page_field.setText("99")  # além do fim: vai para a última, como o Ctrl+G
    viewer.page_field.returnPressed.emit()
    assert viewer._current_page == 3 and viewer.page_field.text() == "4"

    viewer.page_field.setText("")  # apagado: volta ao número da página atual
    viewer.page_field.returnPressed.emit()
    assert viewer._current_page == 3 and viewer.page_field.text() == "4"


def test_fit_page_makes_the_whole_page_visible(viewer):
    viewer._fit_page()

    pixmap = viewer._page_labels[0].pixmap().deviceIndependentSize()
    viewport = viewer.scroll_area.viewport()
    assert pixmap.width() <= viewport.width() and pixmap.height() <= viewport.height()


def test_rotating_the_view_keeps_clicks_on_the_same_place_of_the_page(viewer):
    from core.redaction import RedactionRect

    viewer.redaction_state.set_page_active(True)
    viewer._rotate_view()
    pixmap = viewer._page_labels[0].pixmap().deviceIndependentSize()
    assert pixmap.width() < pixmap.height()  # a página de 400x300 fica de pé na tela

    # Um arrasto sobre a tela girada marca a área certa do PDF: a mesma área marcada pela
    # conversão inversa da geometria girada.
    geometry = viewer._geometry(0)
    left, top = geometry.user_to_screen(40, 260, viewer._scale)
    right, bottom = geometry.user_to_screen(120, 240, viewer._scale)
    viewer._on_canvas_pressed(min(left, right), min(top, bottom))
    viewer._on_canvas_released(max(left, right), max(top, bottom))

    (rect,) = viewer.redaction_state.pending()
    assert isinstance(rect, RedactionRect)
    assert (round(rect.left), round(rect.bottom), round(rect.right), round(rect.top)) == (40, 240, 120, 260)
    assert viewer.session.path()  # o arquivo não muda


def test_search_highlights_every_match_on_the_page(viewer):
    viewer._search_document("palavra")
    while viewer.is_searching():
        viewer._continue_search()

    on_first_page = [m for m in viewer._matches if m.page_index == 0]
    assert len(on_first_page) == 2
    image = viewer._render_with_overlays(0).toImage()
    for match in on_first_page:
        rect = viewer._user_rect_to_screen(0, (match.left, match.bottom, match.right, match.top))
        color = image.pixelColor(int(rect.left()) + 2, int(rect.center().y()))
        assert color.blue() < 200  # pintado de amarelo/laranja, não branco


def test_clicks_land_on_the_page_when_it_is_smaller_than_the_viewer(viewer):
    viewer.redaction_state.set_page_active(True)
    viewer._scale = 0.5
    viewer._apply_zoom()
    canvas = viewer._page_labels[0]
    canvas.resize(2000, 2000)  # o QScrollArea estica o rótulo; a página fica centralizada
    offset = canvas.pixmap_offset()
    assert offset.x() > 0

    received = []
    canvas.mouse_pressed.connect(lambda x, y: received.append((x, y)))
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(offset.x() + 10, offset.y() + 20), QPointF(0, 0),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(event)

    assert received == [(pytest.approx(10), pytest.approx(20))]


def test_dragging_over_text_selects_and_copies_it(viewer):
    geometry = viewer._geometry(0)
    start = geometry.user_to_screen(41, 253, viewer._scale)
    end = geometry.user_to_screen(80, 253, viewer._scale)

    viewer._on_canvas_pressed(*start)
    viewer._on_canvas_moved(*end)
    viewer._on_canvas_released(*end)

    assert viewer.selected_text().startswith("palavra")
    viewer.copy_selected_text()
    assert QApplication.clipboard().text().startswith("palavra")


def test_text_selection_is_off_while_a_markup_tool_is_active(viewer):
    viewer.redaction_state.set_page_active(True)
    geometry = viewer._geometry(0)

    viewer._on_canvas_pressed(*geometry.user_to_screen(41, 253, viewer._scale))
    viewer._on_canvas_released(*geometry.user_to_screen(80, 253, viewer._scale))

    assert viewer.selected_text() == ""


def test_side_panel_lists_bookmarks_and_attachments_and_navigates(tmp_path):
    from pypdf import PdfWriter

    QApplication.instance() or QApplication([])
    source = _pdf(tmp_path / "base.pdf")
    writer = PdfWriter(clone_from=source)
    chapter = writer.add_outline_item("Capítulo 1", 1)
    writer.add_outline_item("Seção 1.1", 2, parent=chapter)
    writer.add_attachment("notas.txt", b"conteudo do anexo")
    path = tmp_path / "com_sumario.pdf"
    writer.write(str(path))
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    session.open(str(path))
    panel = viewer.side_panel

    assert panel.isTabVisible(1) and panel.isTabVisible(2)
    chapter_item = panel.outline_tree.topLevelItem(0)
    assert chapter_item.text(0) == "Capítulo 1" and chapter_item.child(0).text(0) == "Seção 1.1"
    panel._on_outline_clicked(chapter_item.child(0), 0)
    assert viewer._current_page == 2

    from core.attachments import SaveAttachment

    target = tmp_path / "salvo.txt"
    SaveAttachment().run(str(path), "notas.txt", str(target))
    assert target.read_bytes() == b"conteudo do anexo"


def test_side_panel_hides_empty_tabs(viewer):
    panel = viewer.side_panel
    assert not panel.isTabVisible(1) and not panel.isTabVisible(2)
    assert not panel.tabBar().isVisibleTo(panel)


def test_notice_bar_tells_about_forms_signatures_and_layers(tmp_path):
    from core.form_fields import AddFormField
    from core.signature import SignDocument

    QApplication.instance() or QApplication([])
    source = _pdf(tmp_path / "doc.pdf", pages=1)
    with_field = tmp_path / "campo.pdf"
    AddFormField().run(source, str(with_field), field_name="nome", page_number=0, x=20, y=20, field_type="text")
    signed = tmp_path / "assinado.pdf"
    SignDocument().run(str(with_field), str(signed), signer_name="Ana", test_common_name="Ana")
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    requested = []
    viewer.verify_signatures_requested.connect(lambda: requested.append(1))

    session.open(str(signed))

    text = viewer.notice_label.text()
    assert "Assinado digitalmente (1" in text and "formulário (1" in text
    assert viewer.verify_button.isVisibleTo(viewer)
    viewer.verify_button.click()
    assert requested == [1]

    session.open(source)
    assert not viewer.notice_bar.isVisibleTo(viewer)
