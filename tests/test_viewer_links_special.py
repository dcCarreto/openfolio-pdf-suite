"""O que faltava para o visualizador ser um leitor completo: comandos de navegação e links para
outro PDF, links na apresentação, anexos, cópia bloqueada pelo autor, rótulo no campo da página,
ferramenta de mão, Shift + clique, zoom alto e a posição exata de leitura."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from core.page_links import linked_pdf_path, page_links, safe_pdf_file
from core.page_text import can_copy_text
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.preferences import Preferences, preferences, use_preferences
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import CONTINUOUS, SINGLE, PdfViewer
from ui.viewer.presentation import PresentationWindow

NEXT = (70, 695, 190, 715)
OTHER = (70, 645, 190, 665)
TO_END = (70, 595, 190, 615)


def _pdf(path, pages=4) -> str:
    canvas = rl_canvas.Canvas(str(path), pagesize=(612, 792))
    for number in range(pages):
        canvas.setFont("Helvetica", 14)
        canvas.drawString(72, 700, f"palavra pagina {number + 1}")
        canvas.showPage()
    canvas.save()
    return str(path)


def _with_links(path, *links) -> str:
    """Anota `(rect, ação)` na primeira página."""
    writer = PdfWriter(clone_from=path)
    for rect, action in links:
        writer.add_annotation(
            0,
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
                    NameObject("/A"): DictionaryObject({NameObject(k): v for k, v in action.items()}),
                }
            ),
        )
    writer.write(path)
    return path


def _named(name):
    return {"/S": NameObject("/Named"), "/N": NameObject(f"/{name}")}


def _remote(file):
    return {
        "/S": NameObject("/GoToR"),
        "/F": TextStringObject(file),
        "/D": ArrayObject([FloatObject(0), NameObject("/Fit")]),
    }


@pytest.fixture(autouse=True)
def _clean_preferences():
    previous = preferences()
    use_preferences(Preferences())
    yield
    use_preferences(previous)


def _open(path, layout=SINGLE) -> PdfViewer:
    QApplication.instance() or QApplication([])
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.set_layout(layout)
    viewer.resize(800, 700)
    viewer.show()
    session.open(path)
    _settle()
    return viewer


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _click(viewer, rect, modifiers=Qt.KeyboardModifier.NoModifier):
    label = viewer._page_labels[0]
    center = viewer._user_rect_to_screen(viewer._current_page, rect).center() + label.pixmap_offset()
    QTest.mouseClick(label, Qt.MouseButton.LeftButton, modifiers, center.toPoint())
    _settle()


# -- links especiais --------------------------------------------------------------


def test_page_links_reads_named_actions_and_other_pdfs(tmp_path):
    path = _with_links(_pdf(tmp_path / "doc.pdf"), (NEXT, _named("NextPage")), (OTHER, _remote("outro.pdf")))
    document = pdfium.PdfDocument(path)
    page = document[0]
    try:
        links = page_links(document, page, path, 0)
        without_path = page_links(document, page)
    finally:
        page.close()
        document.close()

    assert {(link.named, link.file) for link in links} == {("NextPage", ""), ("", "outro.pdf")}
    assert [link.file for link in without_path] == ["outro.pdf"]


def test_unknown_named_actions_and_other_kinds_of_file_stay_out(tmp_path):
    path = _with_links(
        _pdf(tmp_path / "doc.pdf"),
        (NEXT, _named("Quit")),
        (OTHER, _remote("programa.exe")),
        (TO_END, _remote("//servidor/pasta/a.pdf")),
    )
    document = pdfium.PdfDocument(path)
    page = document[0]
    try:
        assert page_links(document, page, path, 0) == []
    finally:
        page.close()
        document.close()


def test_safe_pdf_file_refuses_the_network_and_other_types(tmp_path):
    assert safe_pdf_file(" capitulo.pdf ") == "capitulo.pdf"
    for blocked in (
        "a.exe",
        "http://x/a.pdf",
        "\\\\servidor\\a.pdf",
        "\\servidor\\a.pdf",
        "//servidor/a.pdf",
        "::servidor:a.pdf",  # como o pdfium reescreve no macOS
        "",
    ):
        assert safe_pdf_file(blocked) == ""
    (tmp_path / "b.pdf").write_bytes(b"%PDF")
    assert linked_pdf_path("b.pdf", str(tmp_path)) == str(tmp_path / "b.pdf")
    assert linked_pdf_path("nao_existe.pdf", str(tmp_path)) == ""


def _first_file(path):
    document = pdfium.PdfDocument(path)
    page = document[0]
    try:
        return [link.file for link in page_links(document, page, path, 0)]
    finally:
        page.close()
        document.close()


def test_the_file_name_comes_as_written_in_the_pdf_on_every_system(tmp_path):
    path = _with_links(_pdf(tmp_path / "doc.pdf"), (OTHER, _remote("sub/pasta/outro.pdf")))
    assert _first_file(path) == ["sub/pasta/outro.pdf"]


def test_a_file_specification_dictionary_is_read_too(tmp_path):
    specification = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): TextStringObject("antigo.pdf"),
            NameObject("/UF"): TextStringObject("outro.pdf"),
        }
    )
    path = _with_links(_pdf(tmp_path / "doc.pdf"), (OTHER, {**_remote("x.pdf"), "/F": specification}))
    assert _first_file(path) == ["outro.pdf"]


@pytest.mark.parametrize(
    ("name", "start", "expected"),
    [("NextPage", 0, 1), ("PrevPage", 2, 1), ("FirstPage", 2, 0), ("LastPage", 0, 3)],
)
def test_named_links_navigate(tmp_path, name, start, expected):
    viewer = _open(_with_links(_pdf(tmp_path / "doc.pdf"), (NEXT, _named(name))))
    link = viewer._page_links(0)[0]
    viewer._go_to_page(start)
    viewer._follow_link(link)
    assert viewer._current_page == expected
    assert viewer._link_tip(link)
    viewer.close_document()


def test_clicking_a_named_link_on_the_page(tmp_path):
    viewer = _open(_with_links(_pdf(tmp_path / "doc.pdf"), (NEXT, _named("NextPage"))))
    _click(viewer, NEXT)
    assert viewer._current_page == 1
    viewer.close_document()


def test_a_link_to_another_pdf_opens_it_next_to_the_document(tmp_path):
    other = _pdf(tmp_path / "outro.pdf", pages=2)
    viewer = _open(_with_links(_pdf(tmp_path / "doc.pdf"), (OTHER, _remote("outro.pdf"))))
    opened = []
    viewer.open_path = opened.append
    _click(viewer, OTHER)
    assert opened == [other]
    viewer.close_document()


def test_a_link_to_a_missing_pdf_only_says_so(tmp_path):
    viewer = _open(_with_links(_pdf(tmp_path / "doc.pdf"), (OTHER, _remote("sumiu.pdf"))))
    opened = []
    viewer.open_path = opened.append
    _click(viewer, OTHER)
    assert opened == []
    viewer.close_document()


# -- apresentação -----------------------------------------------------------------


def _presentation(path) -> PresentationWindow:
    QApplication.instance() or QApplication([])
    window = PresentationWindow(path, 0)
    window.resize(1000, 800)
    window.show()
    window._render()
    return window


def _window_point(window, rect) -> QPoint:
    pixmap = window.label.pixmap().deviceIndependentSize()
    left, bottom, right, top = rect
    x = (left + right) / 2 * window._scale + (window.width() - pixmap.width()) / 2
    y = (792 - (bottom + top) / 2) * window._scale + (window.height() - pixmap.height()) / 2
    return QPoint(int(x), int(y))


def test_presentation_follows_links_and_a_click_elsewhere_advances(tmp_path):
    canvas = rl_canvas.Canvas(str(tmp_path / "doc.pdf"), pagesize=(612, 792))
    canvas.drawString(72, 700, "fim")
    canvas.linkRect("", "fim", TO_END)
    for _ in range(3):
        canvas.showPage()
    canvas.bookmarkPage("fim")
    canvas.showPage()
    canvas.save()
    window = _presentation(str(tmp_path / "doc.pdf"))

    assert window.link_at(QPointF(_window_point(window, TO_END))) is not None
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _window_point(window, TO_END))
    assert window.page() == 3

    window.go_to(0)
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
    assert window.page() == 1
    window.close()


def test_presentation_shows_the_cursor_only_over_a_link(tmp_path):
    window = _presentation(_with_links(_pdf(tmp_path / "doc.pdf"), (NEXT, _named("LastPage"))))
    point = QPointF(_window_point(window, NEXT))

    for where, shape in ((point, Qt.CursorShape.PointingHandCursor), (QPointF(5, 5), Qt.CursorShape.BlankCursor)):
        window.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove, where, where,
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            )
        )
        assert window.cursor().shape() == shape
    window.close()


# -- anexos -----------------------------------------------------------------------


def _with_attachments(tmp_path) -> str:
    inner = _pdf(tmp_path / "interno.pdf", pages=2)
    source = _pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    with open(inner, "rb") as file:
        writer.add_attachment("interno.pdf", file.read())
    writer.add_attachment("programa.exe", b"MZ")
    writer.write(source)
    return source


def _attachment(panel, name):
    items = [panel.attachments_list.item(i) for i in range(panel.attachments_list.count())]
    return next(item for item in items if item.text().startswith(name))


def test_an_attached_pdf_opens_and_other_files_are_only_saved(tmp_path, monkeypatch):
    viewer = _open(_with_attachments(tmp_path))
    panel = viewer.side_panel
    opened, saved = [], []
    viewer.open_path = opened.append
    monkeypatch.setattr(panel, "_save_attachment", saved.append)

    panel._on_attachment_activated(_attachment(panel, "interno.pdf"))
    assert len(opened) == 1 and os.path.basename(opened[0]) == "interno.pdf"
    document = pdfium.PdfDocument(opened[0])
    assert len(document) == 2
    document.close()

    panel._on_attachment_activated(_attachment(panel, "programa.exe"))
    assert saved == ["programa.exe"] and len(opened) == 1
    viewer.close_document()


def test_the_attachment_menu_only_offers_opening_a_pdf(tmp_path):
    viewer = _open(_with_attachments(tmp_path))
    panel = viewer.side_panel
    texts = lambda name: [a.text() for a in panel.attachment_menu(_attachment(panel, name)).actions()]  # noqa: E731
    assert texts("interno.pdf") == ["Abrir", "Salvar como..."]
    assert texts("programa.exe") == ["Salvar como..."]
    viewer.close_document()


# -- cópia bloqueada --------------------------------------------------------------


def _locked(tmp_path) -> str:
    source = _pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    writer.encrypt(user_password="", owner_password="dono", permissions_flag=UserAccessPermissions.PRINT, algorithm="AES-256")
    writer.write(source)
    return source


def test_copy_follows_the_permission_of_the_author(tmp_path):
    QApplication.instance() or QApplication([])
    QApplication.clipboard().setText("antes")
    viewer = _open(_locked(tmp_path))
    with_lock = viewer._document
    assert not can_copy_text(with_lock)

    viewer.select_all_text()
    viewer.copy_selected_text()
    assert QApplication.clipboard().text() == "antes"

    menu = viewer._context_menu(viewer._page_labels[0].mapToGlobal(QPoint(5, 5)))
    action = next(a for a in menu.actions() if a.text().startswith("Copiar"))
    assert action.text() == "Copiar (bloqueado pelo autor)" and not action.isEnabled()
    viewer.close_document()


def test_a_plain_pdf_copies_normally(tmp_path):
    viewer = _open(_pdf(tmp_path / "doc.pdf"))
    assert can_copy_text(viewer._document)
    viewer.select_all_text()
    viewer.copy_selected_text()
    assert "pagina 4" in QApplication.clipboard().text()
    viewer.close_document()


# -- campo da página --------------------------------------------------------------


def test_the_page_field_accepts_the_label_of_the_pdf(tmp_path):
    source = _pdf(tmp_path / "doc.pdf")
    writer = PdfWriter(clone_from=source)
    writer.set_page_label(0, 3, "/r")
    writer.write(source)
    viewer = _open(source)

    viewer.page_field.setText("III")
    viewer.page_field.returnPressed.emit()
    assert viewer._current_page == 2 and viewer.page_field.text() == "3"

    viewer.page_field.setText("zzz")  # não existe: fica onde está
    viewer.page_field.returnPressed.emit()
    assert viewer._current_page == 2 and viewer.page_field.text() == "3"
    viewer.close_document()


# -- ferramenta de mão ------------------------------------------------------------


def _left_drag(viewer, start, end):
    label = viewer._page_labels[0]
    QTest.mousePress(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    global_end = QPointF(label.mapToGlobal(end))
    QApplication.sendEvent(
        label,
        QMouseEvent(
            QEvent.Type.MouseMove, QPointF(end), global_end,
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ),
    )
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def test_hand_tool_drags_the_page_instead_of_selecting(tmp_path):
    viewer = _open(_pdf(tmp_path / "doc.pdf"))
    viewer._set_zoom(200)
    _settle()
    bar = viewer.scroll_area.verticalScrollBar()
    bar.setValue(200)
    viewer.set_hand_mode(True)
    assert viewer.hand_button.isChecked()
    assert viewer._page_labels[0].cursor().shape() == Qt.CursorShape.OpenHandCursor

    _left_drag(viewer, QPoint(300, 500), QPoint(300, 450))

    assert bar.value() == 250
    assert viewer.selected_text() == ""
    assert viewer._pan_from is None

    viewer.set_hand_mode(False)
    assert viewer._page_labels[0].cursor().shape() == Qt.CursorShape.IBeamCursor
    viewer.close_document()


def test_hand_tool_still_clicks_links_but_a_drag_does_not(tmp_path):
    viewer = _open(_with_links(_pdf(tmp_path / "doc.pdf"), (NEXT, _named("NextPage"))))
    viewer.set_hand_mode(True)
    label = viewer._page_labels[0]
    center = (viewer._user_rect_to_screen(0, NEXT).center() + label.pixmap_offset()).toPoint()

    _left_drag(viewer, center, center + QPoint(0, 30))
    assert viewer._current_page == 0

    _click(viewer, NEXT)
    assert viewer._current_page == 1
    viewer.close_document()


# -- Shift + clique ---------------------------------------------------------------


def test_shift_click_extends_the_selection_to_another_page_in_single_mode(tmp_path):
    viewer = _open(_pdf(tmp_path / "doc.pdf"))
    label = viewer._page_labels[0]
    word = viewer._user_rect_to_screen(0, (72, 695, 120, 712)).center() + label.pixmap_offset()
    QTest.mouseDClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, word.toPoint())
    assert viewer.selected_text() == "palavra"

    viewer._go_next()
    _settle()
    label = viewer._page_labels[0]
    QTest.qWait(QApplication.doubleClickInterval() + 20)  # não é o terceiro clique
    QTest.mouseClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, word.toPoint())

    first, second = viewer.selected_text().split("\n")
    assert first == "palavra pagina 1" and "palavra".startswith(second) and second
    assert viewer._text_selection[0] == 0 and viewer._text_selection[2] == 1
    viewer.close_document()


# -- zoom e posição ---------------------------------------------------------------


def test_zoom_goes_up_to_800_percent(tmp_path):
    viewer = _open(_pdf(tmp_path / "doc.pdf"))
    viewer._set_zoom(800)
    assert viewer._scale == 8.0
    viewer._set_zoom(5000)
    assert viewer._scale == 8.0
    assert viewer._page_labels[0].pixmap().deviceIndependentSize().width() == pytest.approx(612 * 8, abs=2)
    viewer.close_document()


@pytest.mark.parametrize("layout", [SINGLE, CONTINUOUS])
def test_reopening_returns_to_the_exact_point_of_the_page(tmp_path, layout):
    path = _pdf(tmp_path / "doc.pdf")
    viewer = _open(path, layout)
    viewer._show_view(2, 0.25)
    _settle()
    page, fraction = viewer._view_position()
    assert page == 2 and fraction > 0.1
    viewer.close_document()

    again = _open(path, layout)
    _settle()
    new_page, new_fraction = again._view_position()
    assert new_page == 2 and new_fraction == pytest.approx(fraction, abs=0.03)
    again.close_document()
