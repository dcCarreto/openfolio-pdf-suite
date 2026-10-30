"""O visualizador como leitor de PDF: histórico (Voltar), seleção de texto em todos os modos,
palavra e linha, menu do botão direito, notas, teclado, roda do mouse, ajuste que acompanha a
janela, posição de leitura, visão inicial do PDF, rótulos de página, busca e formulários na
rolagem."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, Fit, FloatObject, NameObject, NumberObject, TextStringObject
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from reportlab.pdfgen import canvas as rl_canvas

from core.bookmarks import ListOutline
from core.document_info import initial_view
from core.form_fields import ListFormFields
from core.page_links import page_notes
from core.page_text import char_at, line_range, word_range
from tests.test_form_fields import _build_pdf_with_various_fields
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.preferences import Preferences, preferences, use_preferences
from ui.redaction_state import RedactionState
from ui.tasks import wait_for_tasks
from ui.viewer.pdf_viewer import BOOK, CONTINUOUS, DOUBLE, SINGLE, PdfViewer

LINK_RECT = (70, 695, 190, 715)
LINE_Y = 700


def _reading_pdf(path, pages=5) -> str:
    canvas = rl_canvas.Canvas(str(path), pagesize=(612, 792))
    canvas.setFont("Helvetica", 14)
    canvas.drawString(72, LINE_Y, "Ir para o fim")
    canvas.linkRect("", "fim", LINK_RECT)
    canvas.drawString(72, 600, "primeira linha da pagina")
    canvas.showPage()
    for number in range(1, pages):
        if number == pages - 1:
            canvas.bookmarkPage("fim", fit="XYZ", top=300)
        canvas.setFont("Helvetica", 14)
        canvas.drawString(72, LINE_Y, f"palavra alfa pagina {number + 1}")
        canvas.showPage()
    canvas.save()
    return str(path)


@pytest.fixture(autouse=True)
def _clean_preferences():
    previous = preferences()
    use_preferences(Preferences())
    yield
    use_preferences(previous)


def _open(path, layout=SINGLE, size=(800, 700)) -> PdfViewer:
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.set_layout(layout)
    viewer.resize(*size)
    viewer.show()
    session.open(path)
    QApplication.processEvents()
    return viewer


@pytest.fixture
def viewer(tmp_path):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"))
    yield viewer
    viewer.close_document()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _point(viewer, page, x, y) -> tuple[float, float]:
    screen_x, screen_y = viewer._geometry(page).user_to_screen(x, y, viewer._scale)
    return screen_x, screen_y


def _label(viewer, page):
    return viewer._page_labels[page if viewer._continuous else 0]


def _drag(viewer, start_page, start, end_page, end):
    """Um arrasto como o mouse faz: o rótulo em que apertou recebe tudo até soltar."""
    label = _label(viewer, start_page)
    source = viewer._page_labels[start_page if viewer._continuous else 0]
    target = _label(viewer, end_page)
    press = QPointF(*_point(viewer, start_page, *start))
    offset = source.pixmap_offset()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, (press + offset).toPoint())
    end_point = (QPointF(*_point(viewer, end_page, *end)) + target.pixmap_offset()).toPoint()
    destination = label.mapFromGlobal(target.mapToGlobal(end_point))
    QApplication.sendEvent(
        label,
        QMouseEvent(
            QEvent.Type.MouseMove, QPointF(destination), QPointF(label.mapToGlobal(destination)),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ),
    )
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, destination)


def _wheel(delta, modifiers=Qt.KeyboardModifier.NoModifier, position=None):
    position = position or QPointF(50, 50)
    return QWheelEvent(
        position, position, QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
    )


# -- histórico --------------------------------------------------------------------


@pytest.mark.parametrize("layout", [SINGLE, CONTINUOUS])
def test_back_and_forward_return_from_a_link(tmp_path, layout):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"), layout)
    link = viewer._page_links(0)[0]

    viewer._follow_link(link)
    _settle()
    assert viewer._current_page == 4

    viewer.go_back()
    _settle()
    assert viewer._current_page == 0
    viewer.go_forward()
    _settle()
    assert viewer._current_page == 4
    viewer.close_document()


def test_a_new_jump_clears_forward_and_page_turns_do_not_enter_the_history(viewer):
    viewer._go_next()
    assert viewer._back == []  # virar a página não é um salto

    viewer._jump_to_page(3)
    viewer.go_back()
    assert viewer._forward
    viewer._jump_to_page(2)
    assert viewer._forward == []


def test_mouse_back_button_goes_back(viewer):
    viewer._jump_to_page(3)
    label = viewer._page_labels[0]
    QTest.mouseClick(label, Qt.MouseButton.BackButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
    _settle()
    assert viewer._current_page == 0


def test_a_new_version_keeps_the_history_and_another_document_clears_it(viewer, tmp_path):
    viewer._jump_to_page(3)
    assert viewer._back
    viewer.session.open(_reading_pdf(tmp_path / "outro.pdf"))
    assert viewer._back == [] and viewer._forward == []


def test_closing_right_after_navigating_leaves_nothing_pending(tmp_path):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"))
    viewer._go_next()  # deixa o ajuste da rolagem para depois do layout
    viewer.close_document()
    viewer.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _settle()  # um disparo pendente sobre o visualizador apagado derrubaria o processo aqui


# -- seleção de texto -------------------------------------------------------------


@pytest.mark.parametrize("layout", [SINGLE, CONTINUOUS, DOUBLE, BOOK])
def test_dragging_selects_text_in_every_layout(tmp_path, layout):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"), layout)
    _settle()
    _drag(viewer, 1, (73, LINE_Y + 3), 1, (125, LINE_Y + 3)) if layout != SINGLE else _drag(
        viewer, 0, (73, 603), 0, (125, 603)
    )
    expected = "primeira" if layout == SINGLE else "palavra"
    assert expected in viewer.selected_text()
    viewer.close_document()


def test_a_drag_in_continuous_mode_can_cross_pages(tmp_path):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"), CONTINUOUS, size=(800, 2000))
    _settle()
    _drag(viewer, 1, (73, LINE_Y + 3), 2, (125, LINE_Y + 3))
    first, second = viewer.selected_text().split("\n")
    assert first.endswith("pagina 2") and second.startswith("palavra") and "pagina 3" not in second
    assert viewer._text_selection[0] == 1 and viewer._text_selection[2] == 2
    viewer.close_document()


def test_a_click_selects_nothing_and_clears_the_selection(viewer):
    x, y = _point(viewer, 0, 73, 603)
    viewer._on_canvas_pressed(x, y)
    viewer._on_canvas_released(x, y)
    assert viewer.selected_text() == ""

    viewer.select_all_text()
    assert viewer.selected_text()
    viewer._on_canvas_pressed(x, y)
    viewer._on_canvas_released(x, y)
    assert viewer.selected_text() == ""


def test_double_click_selects_the_word_and_triple_click_the_line(viewer):
    label = viewer._page_labels[0]
    position = QPointF(*_point(viewer, 0, 80, 604)) + label.pixmap_offset()
    QTest.mouseDClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position.toPoint())
    assert viewer.selected_text() == "primeira"

    QTest.mouseClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position.toPoint())
    assert viewer.selected_text() == "primeira linha da pagina"


def test_select_all_takes_the_whole_document_and_copies_it(viewer):
    viewer.select_all_text()
    viewer.copy_selected_text()
    text = QApplication.clipboard().text()
    assert "Ir para o fim" in text and "pagina 5" in text


def test_the_selection_is_painted_over_the_page_and_follows_the_zoom(viewer):
    viewer.select_all_text()
    label = viewer._page_labels[0]
    first = label._selection_rects[0]
    assert label._selection_rects
    viewer._set_zoom(200)
    assert label._selection_rects[0].width() > first.width()
    viewer._clear_text_selection()
    assert label._selection_rects == []


def test_page_text_helpers_find_word_and_line(tmp_path):
    document = pdfium.PdfDocument(_reading_pdf(tmp_path / "doc.pdf"))
    page = document[0]
    textpage = page.get_textpage()
    try:
        index = char_at(textpage, 80, 604)
        start, count = word_range(textpage, index)
        assert textpage.get_text_range(start, count) == "primeira"
        start, count = line_range(textpage, index)
        assert textpage.get_text_range(start, count) == "primeira linha da pagina"
        assert char_at(textpage, 500, 100, exact=True) is None
        assert char_at(textpage, 400, 604) is not None  # o mais próximo, para o arrasto
    finally:
        textpage.close()
        page.close()
        document.close()


# -- menu do botão direito --------------------------------------------------------


def _menu_texts(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_context_menu_offers_copy_navigation_and_view(viewer):
    menu = viewer._context_menu(viewer._page_labels[0].mapToGlobal(QPoint(5, 5)))
    texts = _menu_texts(menu)
    for text in ("Copiar", "Selecionar tudo", "Voltar", "Avançar", "Aumentar zoom", "Ajustar à largura"):
        assert text in texts
    actions = {action.text(): action for action in menu.actions()}
    assert not actions["Copiar"].isEnabled() and not actions["Voltar"].isEnabled()


def test_context_menu_on_a_link_copies_its_address(tmp_path):
    path = str(tmp_path / "site.pdf")
    canvas = rl_canvas.Canvas(path, pagesize=(612, 792))
    canvas.drawString(72, 700, "site")
    canvas.linkURL("https://example.com/a", LINK_RECT)
    canvas.showPage()
    canvas.save()
    viewer = _open(path)
    label = viewer._page_labels[0]
    center = viewer._user_rect_to_screen(0, LINK_RECT).center() + label.pixmap_offset()

    menu = viewer._context_menu(label.mapToGlobal(center.toPoint()))

    actions = {action.text(): action for action in menu.actions()}
    assert "Abrir link" in actions
    actions["Copiar endereço do link"].trigger()
    assert QApplication.clipboard().text() == "https://example.com/a"
    viewer.close_document()


def test_right_click_keeps_the_selection(viewer):
    viewer.select_all_text()
    label = viewer._page_labels[0]
    QTest.mousePress(label, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
    QTest.mouseRelease(label, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
    assert viewer.selected_text()


# -- notas ------------------------------------------------------------------------


def _with_note(path, author="Ana", content="Revisar <b>isto</b>"):
    writer = PdfWriter(clone_from=path)
    writer.add_annotation(
        0,
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Text"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (300, 300, 330, 330)]),
                NameObject("/Contents"): TextStringObject(content),
                NameObject("/T"): TextStringObject(author),
            }
        ),
    )
    writer.write(path)
    return path


def test_page_notes_reads_only_comments_with_text(tmp_path):
    path = _with_note(_reading_pdf(tmp_path / "doc.pdf"))
    document = pdfium.PdfDocument(path)
    page = document[0]
    try:
        notes = page_notes(page)
    finally:
        page.close()
        document.close()
    assert [(n.author, n.content) for n in notes] == [("Ana", "Revisar <b>isto</b>")]
    assert notes[0].contains(310, 310)


def test_hovering_a_note_shows_it_with_the_pdf_text_escaped(tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("ui.viewer.pdf_viewer.QToolTip.showText", lambda _pos, text, _w=None: shown.append(text))
    viewer = _open(_with_note(_reading_pdf(tmp_path / "doc.pdf")))
    canvas = viewer._page_labels[0]

    viewer._on_page_hovered(canvas, 0, *_point(viewer, 0, 310, 310))

    assert shown and "<b>Ana</b>" in shown[0] and "&lt;b&gt;isto&lt;/b&gt;" in shown[0]
    viewer.close_document()


# -- teclado e roda ---------------------------------------------------------------


def test_wheel_past_the_page_edge_turns_the_page_only_in_single_mode(viewer):
    viewport = viewer.scroll_area.viewport()
    viewer._set_zoom(50)  # a página inteira cabe: já está nas duas bordas
    _settle()

    assert viewer.eventFilter(viewport, _wheel(-120))
    assert viewer._current_page == 1
    assert viewer.eventFilter(viewport, _wheel(120))
    assert viewer._current_page == 0


def test_small_trackpad_steps_add_up_to_one_page_turn(viewer):
    viewport = viewer.scroll_area.viewport()
    viewer._set_zoom(50)
    _settle()
    for _ in range(3):
        viewer.eventFilter(viewport, _wheel(-30))
    assert viewer._current_page == 0
    viewer.eventFilter(viewport, _wheel(-30))
    assert viewer._current_page == 1


def test_wheel_inside_a_tall_page_just_scrolls(viewer):
    viewer._set_zoom(200)
    _settle()
    assert viewer.scroll_area.verticalScrollBar().maximum() > 0

    assert not viewer.eventFilter(viewer.scroll_area.viewport(), _wheel(-120))
    assert viewer._current_page == 0


def test_going_up_past_the_top_shows_the_end_of_the_previous_page(viewer):
    viewer._set_zoom(200)
    _settle()
    viewer._go_next()
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    assert bar.value() == 0

    viewer._scroll_view(-1, 40)
    _settle()

    assert viewer._current_page == 0 and bar.value() == bar.maximum() > 0


def test_turning_the_page_starts_at_its_top(viewer):
    viewer._set_zoom(200)
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    bar.setValue(bar.maximum())

    viewer._go_next()
    _settle()

    assert bar.value() == 0


def test_space_scrolls_a_screen_and_keeps_some_overlap(tmp_path):
    viewer = _open(_reading_pdf(tmp_path / "doc.pdf"), CONTINUOUS)
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    viewer.scroll_area.setFocus()

    viewer._scroll_view(1, viewer._screen_step())

    assert bar.value() == viewer.scroll_area.viewport().height() - 40
    viewer.close_document()


def test_opening_a_document_gives_the_keyboard_to_the_page(viewer):
    assert viewer.focusWidget() is viewer.scroll_area


# -- zoom -------------------------------------------------------------------------


@pytest.mark.parametrize("fit", ["_fit_width", "_fit_page"])
def test_fit_follows_the_window_until_another_zoom_is_chosen(viewer, fit):
    getattr(viewer, fit)()
    before = viewer._scale
    viewer.resize(1200, 1000)
    QApplication.processEvents()
    viewer._refit()  # o que o timer faria ao fim do redimensionamento
    assert viewer._scale > before

    viewer._set_zoom(100)
    viewer.resize(800, 700)
    QApplication.processEvents()
    viewer._refit()
    assert viewer._scale == 1.0


def test_ctrl_wheel_keeps_the_point_under_the_mouse(viewer):
    viewer._set_zoom(200)
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    _settle()
    position = QPointF(200, 300)
    content = viewer.scroll_area.widget()
    fraction = (bar.value() + position.y()) / content.height()

    viewer.eventFilter(viewer.scroll_area.viewport(), _wheel(120, Qt.KeyboardModifier.ControlModifier, position))
    _settle()

    assert (bar.value() + position.y()) / viewer.scroll_area.widget().height() == pytest.approx(fraction, abs=0.01)


def test_middle_button_drags_the_page(viewer):
    viewer._set_zoom(200)
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    bar.setValue(100)
    viewport = viewer.scroll_area.viewport()

    def event(kind, y, button, buttons):
        at = QPointF(50, y)
        return QMouseEvent(kind, at, at, button, buttons, Qt.KeyboardModifier.NoModifier)

    middle = Qt.MouseButton.MiddleButton
    assert viewer.eventFilter(viewport, event(QEvent.Type.MouseButtonPress, 200, middle, middle))
    assert viewer.eventFilter(viewport, event(QEvent.Type.MouseMove, 170, Qt.MouseButton.NoButton, middle))
    assert bar.value() == 130
    assert viewer.eventFilter(viewport, event(QEvent.Type.MouseButtonRelease, 170, middle, Qt.MouseButton.NoButton))
    assert viewer._pan_from is None


# -- abrir ------------------------------------------------------------------------


def test_reopening_a_document_returns_to_where_the_reading_stopped(tmp_path):
    path = _reading_pdf(tmp_path / "doc.pdf")
    viewer = _open(path)
    viewer._go_to_page(3)
    viewer.close_document()

    again = _open(path)
    assert again._current_page == 3 and again.page_field.text() == "4"
    again.close_document()


def test_preferences_forget_the_oldest_positions():
    prefs = Preferences()
    for number in range(205):
        prefs.set_reading_position(f"doc{number}.pdf", 2)
    assert prefs.reading_position("doc204.pdf") == (2, 0.0)
    assert prefs.reading_position("doc0.pdf") is None
    prefs.set_reading_position("doc204.pdf", 0)
    assert prefs.reading_position("doc204.pdf") is None


def _with_catalog(path, **entries):
    writer = PdfWriter(clone_from=path)
    for key, value in entries.items():
        make = value(writer) if callable(value) else value
        writer.root_object[NameObject(f"/{key}")] = make
    writer.write(path)
    return path


def _go_to_page_action(page, top=None):
    def build(writer):
        fit = [NameObject("/XYZ"), NumberObject(0), NumberObject(top), NumberObject(0)] if top else [NameObject("/Fit")]
        return ArrayObject([writer.pages[page].indirect_reference, *fit])

    return build


def test_initial_view_reads_what_the_pdf_asks_for(tmp_path):
    path = _with_catalog(
        _reading_pdf(tmp_path / "doc.pdf"),
        OpenAction=_go_to_page_action(2, 400),
        PageLayout=NameObject("/TwoColumnRight"),
        PageMode=NameObject("/UseOutlines"),
    )
    view = initial_view(path)
    assert (view.page, view.top, view.layout, view.panel) == (2, 400, "book", "outline")


def test_initial_view_reads_a_goto_action_and_survives_a_plain_pdf(tmp_path):
    plain = _reading_pdf(tmp_path / "plain.pdf")
    assert initial_view(plain).page == 0 and initial_view(plain).layout == ""

    def action(writer):
        return DictionaryObject({NameObject("/S"): NameObject("/GoTo"), NameObject("/D"): _go_to_page_action(1)(writer)})

    assert initial_view(_with_catalog(_reading_pdf(tmp_path / "doc.pdf"), OpenAction=action)).page == 1
    assert initial_view(str(tmp_path / "nao_existe.pdf")).page == 0


def test_the_pdf_opens_where_it_asks_and_the_full_screen_mode_is_ignored(tmp_path):
    path = _with_catalog(
        _reading_pdf(tmp_path / "doc.pdf"), OpenAction=_go_to_page_action(2), PageMode=NameObject("/FullScreen")
    )
    viewer = _open(path)
    assert viewer._current_page == 2 and not viewer.isFullScreen()
    viewer.close_document()


def test_the_saved_reading_position_wins_over_the_pdf(tmp_path):
    path = _with_catalog(_reading_pdf(tmp_path / "doc.pdf"), OpenAction=_go_to_page_action(2))
    preferences().set_reading_position(path, 4)
    viewer = _open(path)
    assert viewer._current_page == 4
    viewer.close_document()


def test_the_layout_of_the_pdf_applies_only_until_the_user_chooses_one(tmp_path):
    path = _with_catalog(_reading_pdf(tmp_path / "doc.pdf"), PageLayout=NameObject("/TwoPageLeft"))
    viewer = _open(path)
    assert viewer.page_layout() == DOUBLE
    assert preferences().page_layout() is None  # o PDF não muda a preferência de quem lê
    viewer.close_document()

    preferences().set_page_layout(SINGLE)
    viewer = _open(path)
    assert viewer.page_layout() == SINGLE
    viewer.close_document()


def test_the_bookmarks_panel_opens_when_the_pdf_asks(tmp_path):
    source = _reading_pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    writer.add_outline_item("Capítulo", 1)
    writer.write(source)
    viewer = _open(_with_catalog(source, PageMode=NameObject("/UseOutlines")))
    assert viewer.side_panel.currentIndex() == 1
    viewer.close_document()


def test_page_labels_of_the_pdf_appear_next_to_the_total(tmp_path):
    source = _reading_pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    writer.set_page_label(0, 1, "/r")
    writer.write(source)
    viewer = _open(source)
    assert viewer.page_total.text() == "de 5 (i)" and viewer.page_field.text() == "1"
    viewer._go_to_page(1)
    assert viewer.page_total.text() == "de 5 (ii)"
    viewer.close_document()


# -- marcadores -------------------------------------------------------------------


def _outline_pdf(tmp_path) -> str:
    source = _reading_pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    writer.add_outline_item("Alto", 2, fit=Fit.xyz(top=300))
    for title, url in (("Site", "https://example.com/s"), ("Bloqueado", "file:///C:/x.exe")):
        node = writer.add_outline_item(title, 0).get_object()
        node.pop(NameObject("/Dest"), None)
        node[NameObject("/A")] = DictionaryObject(
            {NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject(url)}
        )
    writer.write(source)
    return source


def test_outline_gives_the_height_and_only_safe_sites(tmp_path):
    items = ListOutline().run(_outline_pdf(tmp_path))
    assert (items[0].page_index, items[0].top) == (2, 300)
    assert items[1].url == "https://example.com/s"
    assert items[2].url == ""


def test_clicking_bookmarks_goes_to_the_height_and_opens_sites(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("ui.viewer.pdf_viewer.QDesktopServices.openUrl", lambda url: opened.append(url.toString()) or True)
    viewer = _open(_outline_pdf(tmp_path), CONTINUOUS)
    _settle()
    tree = viewer.side_panel.outline_tree

    viewer.side_panel._on_outline_clicked(tree.topLevelItem(0), 0)
    _settle()
    value = viewer.scroll_area.verticalScrollBar().value()
    assert viewer._page_tops[2] < value < viewer._page_tops[2] + viewer._page_labels[2].height()
    assert viewer._back  # Voltar traz do marcador

    viewer.side_panel._on_outline_clicked(tree.topLevelItem(1), 0)
    assert opened == ["https://example.com/s"]
    viewer.close_document()


# -- busca ------------------------------------------------------------------------


def _finish_search(viewer):
    while viewer.is_searching():
        viewer._continue_search()


def test_enter_searches_then_steps_and_f3_steps_too(viewer):
    bar = viewer.search_bar
    bar.show()
    bar.query_edit.setText("palavra")
    bar.query_edit.returnPressed.emit()
    _finish_search(viewer)
    assert len(viewer._matches) == 4 and viewer._current_match == 0

    bar.query_edit.returnPressed.emit()
    assert viewer._current_match == 1
    viewer._step_search(1)
    assert viewer._current_match == 2
    viewer._step_search(-1)
    assert viewer._current_match == 1

    bar.query_edit.setText("alfa")  # outro termo: Enter busca de novo
    bar.query_edit.returnPressed.emit()
    _finish_search(viewer)
    assert viewer._current_match == 0


def test_search_options_narrow_the_matches(tmp_path):
    canvas = rl_canvas.Canvas(str(tmp_path / "doc.pdf"), pagesize=(612, 792))
    canvas.drawString(72, 700, "Casa casa casamento")
    canvas.showPage()
    canvas.save()
    viewer = _open(str(tmp_path / "doc.pdf"))
    bar = viewer.search_bar
    bar.query_edit.setText("casa")

    def count():
        _finish_search(viewer)
        return len(viewer._matches)

    bar.query_edit.returnPressed.emit()
    assert count() == 3
    bar.case_check.setChecked(True)
    assert count() == 2
    bar.word_check.setChecked(True)
    assert count() == 1
    viewer.close_document()


def test_ctrl_f_starts_from_the_selected_text(viewer):
    x, y = _point(viewer, 0, 80, 604)
    viewer._select_around(0, x, y, word_range)
    viewer._toggle_search()
    assert viewer.search_bar.query() == "primeira"


def test_going_back_returns_from_a_search_match(viewer):
    viewer.search_bar.query_edit.setText("alfa")
    viewer.search_bar.query_edit.returnPressed.emit()
    _finish_search(viewer)
    assert viewer._current_page == 1
    viewer.go_back()
    assert viewer._current_page == 0


def test_escape_closes_the_search_bar(viewer):
    viewer._toggle_search()
    assert viewer.search_bar.isVisible()
    viewer.search_bar.closed.emit()
    assert not viewer.search_bar.isVisible()


# -- formulários -------------------------------------------------------------------


def _values(path) -> dict[str, str]:
    return {field.name: field.value for field in ListFormFields().run(str(path))}


def _click_field(viewer, name):
    widget = next(w for w in viewer._form_widgets if w.name == name)
    label = viewer._field_canvas(widget)
    center = viewer._user_rect_to_screen(widget.page_index, widget.rect).center() + label.pixmap_offset()
    QTest.mouseClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center.toPoint())


def test_forms_fill_in_continuous_mode_without_losing_the_position(tmp_path):
    viewer = _open(_build_pdf_with_various_fields(tmp_path), CONTINUOUS)
    _settle()

    _click_field(viewer, "nome")
    editor, _widget = viewer._field_editor
    editor.setText("Ana")
    editor.editingFinished.emit()
    assert wait_for_tasks()
    _settle()
    assert _values(viewer.session.path())["nome"] == "Ana"
    assert viewer.page_layout() == CONTINUOUS

    _click_field(viewer, "aceite")
    assert wait_for_tasks()
    assert _values(viewer.session.path())["aceite"] == "/Yes"
    viewer.close_document()


def test_tab_writes_the_field_and_opens_the_next_text_field(tmp_path):
    source = _build_pdf_with_various_fields(tmp_path)
    from core.form_fields import AddFormField

    target = tmp_path / "dois.pdf"
    AddFormField().run(source, str(target), field_name="sobrenome", page_number=0, x=50, y=100, field_type="text")
    viewer = _open(str(target))
    _click_field(viewer, "nome")
    editor, _widget = viewer._field_editor
    editor.setText("Ana")

    viewer._tab_to_field(1)
    assert wait_for_tasks()
    _settle()

    assert _values(viewer.session.path())["nome"] == "Ana"
    assert viewer._field_editor is not None and viewer._field_editor[1].name == "sobrenome"

    viewer._tab_to_field(-1)  # sem mudança: abre o anterior sem criar versão
    path = viewer.session.path()
    _settle()
    assert viewer._field_editor[1].name == "nome" and viewer.session.path() == path
    viewer._finish_field_edit(commit=False)
    viewer.close_document()


def test_a_multiline_field_gets_a_multiline_editor(tmp_path):
    source = _build_pdf_with_various_fields(tmp_path)
    writer = PdfWriter(clone_from=source)
    for annotation in writer.pages[0]["/Annots"]:
        node = annotation.get_object()
        if node.get("/T") == "nome":
            node[NameObject("/Ff")] = NumberObject(1 << 12)
    target = tmp_path / "multi.pdf"
    writer.write(str(target))
    viewer = _open(str(target))

    _click_field(viewer, "nome")
    editor, widget = viewer._field_editor
    assert widget.multiline and isinstance(editor, QPlainTextEdit)

    editor.setPlainText("linha 1\nlinha 2")
    viewer._finish_field_edit()
    assert wait_for_tasks()
    assert "linha 2" in _values(viewer.session.path())["nome"]
    viewer.close_document()


def test_undo_keeps_the_page_of_the_document(tmp_path):
    source = _build_pdf_with_various_fields(tmp_path)
    viewer = _open(source)
    _click_field(viewer, "aceite")
    assert wait_for_tasks()
    viewer.session.undo()
    assert viewer._current_page == 0
    viewer.close_document()
