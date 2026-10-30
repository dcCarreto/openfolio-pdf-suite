"""Links no visualizador: os anotados (site e outra página) e os endereços escritos no texto
abrem com um clique, na página única e na rolagem; arrastar seleciona texto, e com uma
ferramenta ativa o clique é dela. Links para programas, arquivos e scripts não saem."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from core.page_links import page_links, safe_url
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import CONTINUOUS, SINGLE, PdfViewer

SITE = (70, 695, 190, 715)
TO_END = (70, 645, 170, 665)
SCRIPT = (300, 300, 400, 320)
LOCAL_FILE = (300, 250, 400, 270)


def _links_pdf(tmp_path) -> str:
    path = str(tmp_path / "links.pdf")
    canvas = rl_canvas.Canvas(path, pagesize=(612, 792))
    canvas.setFont("Helvetica", 14)
    canvas.drawString(72, 700, "Site do projeto")
    canvas.linkURL("https://example.com/a", SITE)
    canvas.drawString(72, 650, "Ir para o fim")
    canvas.linkRect("", "fim", TO_END)
    canvas.drawString(72, 600, "Escreva para contato@exemplo.com ou veja www.exemplo.org")
    canvas.showPage()
    for _ in range(2):  # páginas compridas o bastante para a rolagem precisar andar
        canvas.drawString(72, 700, "Meio")
        canvas.showPage()
    canvas.bookmarkPage("fim", fit="XYZ", top=300)
    canvas.drawString(72, 300, "Fim")
    canvas.showPage()
    canvas.save()

    writer = PdfWriter(clone_from=path)
    for rect, action in (
        (SCRIPT, {"/S": NameObject("/JavaScript"), "/JS": TextStringObject("app.alert(1)")}),
        (LOCAL_FILE, {"/S": NameObject("/URI"), "/URI": TextStringObject("file:///C:/Windows/System32/calc.exe")}),
    ):
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


def test_page_links_reads_sites_pages_and_addresses_in_the_text(tmp_path):
    document = pdfium.PdfDocument(_links_pdf(tmp_path))
    page = document[0]
    try:
        links = page_links(document, page)
    finally:
        page.close()
        document.close()

    assert [(link.url, link.target_page) for link in links] == [
        ("https://example.com/a", None),
        ("", 3),
        ("mailto:contato@exemplo.com", None),
        ("http://www.exemplo.org", None),
    ]
    assert links[0].rect == SITE and links[1].rect == TO_END
    assert links[1].target_top == 300  # a altura do destino, para mostrar o lugar certo


def test_safe_url_only_lets_sites_and_email_through():
    assert safe_url(" https://a.com ") == "https://a.com"
    assert safe_url("www.a.com") == "http://www.a.com"
    assert safe_url("MAILTO:ana@a.com") == "MAILTO:ana@a.com"
    for blocked in ("file:///C:/x.exe", "javascript:alert(1)", "smb://servidor/x", "calc.exe", ""):
        assert safe_url(blocked) == ""


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    opened: list[str] = []
    monkeypatch.setattr(
        "ui.viewer.pdf_viewer.QDesktopServices.openUrl", lambda url: opened.append(url.toString()) or True
    )
    session = DocumentSession()
    session.open(_links_pdf(tmp_path))
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.opened = opened
    viewer.resize(800, 700)
    viewer.show()
    QApplication.processEvents()
    yield viewer
    viewer.close_document()


def _canvas_point(viewer, page: int, rect, dx: float = 0) -> tuple:
    label = viewer._page_labels[page if viewer._continuous else 0]
    center = viewer._user_rect_to_screen(page, rect).center() + label.pixmap_offset() + QPointF(dx, 0)
    return label, center.toPoint()


def _click(viewer, page: int, rect):
    label, point = _canvas_point(viewer, page, rect)
    QTest.mouseClick(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)


@pytest.mark.parametrize("layout", [SINGLE, CONTINUOUS])
def test_clicking_a_site_link_opens_it_in_the_browser(viewer, layout):
    viewer.set_layout(layout)
    QApplication.processEvents()
    _click(viewer, 0, SITE)
    assert viewer.opened == ["https://example.com/a"]


def test_clicking_an_internal_link_shows_the_target_page(viewer):
    viewer.set_layout(SINGLE)
    _click(viewer, 0, TO_END)
    assert viewer._current_page == 3
    assert viewer.opened == []


def test_internal_link_scrolls_to_the_target_in_continuous_mode(viewer):
    viewer.set_layout(CONTINUOUS)
    QApplication.processEvents()
    _click(viewer, 0, TO_END)
    QApplication.processEvents()
    # O "Fim" (altura 300 de 792) fica perto do alto da área visível, não o topo da página.
    value = viewer.scroll_area.verticalScrollBar().value()
    assert viewer._page_tops[3] < value < viewer._page_tops[3] + viewer._page_labels[3].height()


def test_blocked_links_do_nothing(viewer):
    viewer.set_layout(SINGLE)
    _click(viewer, 0, SCRIPT)
    _click(viewer, 0, LOCAL_FILE)
    assert viewer.opened == [] and viewer._current_page == 0


def test_dragging_from_a_link_selects_text_instead(viewer):
    viewer.set_layout(SINGLE)
    label, start = _canvas_point(viewer, 0, SITE, dx=-40)
    _label, end = _canvas_point(viewer, 0, SITE, dx=40)
    QTest.mousePress(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(label, end)
    QApplication.sendEvent(
        label,
        QMouseEvent(
            QEvent.Type.MouseMove, QPointF(end), QPointF(label.mapToGlobal(end)),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ),
    )
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    assert viewer.opened == []
    assert "projeto" in viewer.selected_text()


def test_with_a_markup_tool_the_click_belongs_to_the_tool(viewer):
    viewer.set_layout(SINGLE)
    viewer.annotation_state.set_page_active(True)
    viewer.annotation_state.set_tool("highlight")
    _click(viewer, 0, SITE)
    assert viewer.opened == []


def test_hovering_a_link_shows_the_hand(viewer):
    viewer.set_layout(CONTINUOUS)
    QApplication.processEvents()
    label, point = _canvas_point(viewer, 0, SITE)
    _label, outside = _canvas_point(viewer, 0, SITE, dx=300)
    for where in (point, outside):
        QApplication.sendEvent(
            label,
            QMouseEvent(
                QEvent.Type.MouseMove, QPointF(where), QPointF(label.mapToGlobal(where)),
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            ),
        )
        expected = Qt.CursorShape.PointingHandCursor if where == point else Qt.CursorShape.ArrowCursor
        assert label.cursor().shape() == expected
    assert viewer._link_tip(viewer._page_links(0)[2]) == "Escrever para contato@exemplo.com"
