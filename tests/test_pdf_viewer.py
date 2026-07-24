"""Testes do visualizador de PDF (ui/viewer/pdf_viewer.py e ui/viewer/search.py)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from ui.document_session import DocumentSession
from ui.viewer.pdf_viewer import PdfViewer
from ui.viewer.search import DocumentSearch


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_pdf_with_text(path, texts: list[str]) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(300, 300))
    for text in texts:
        canvas.drawString(50, 250, text)
        canvas.showPage()
    canvas.save()


@pytest.fixture
def three_page_pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["Primeira página", "Segunda página", "Terceira página"])
    return path


def test_viewer_starts_in_empty_state():
    _app()
    viewer = PdfViewer(DocumentSession())
    assert viewer.content_stack.currentIndex() == 0


def test_viewer_loads_document_and_thumbnails(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session)

    session.open(str(three_page_pdf))

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_zoom_in_increases_scale(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session)
    session.open(str(three_page_pdf))

    initial_scale = viewer._scale
    viewer._zoom_in()

    assert viewer._scale > initial_scale


def test_viewer_loads_immediately_if_session_already_has_a_path(three_page_pdf):
    _app()
    session = DocumentSession()
    session.open(str(three_page_pdf))

    # Simula o rebuild da UI ao trocar de idioma: o PdfViewer é reconstruído
    # depois que a sessão já tinha um documento aberto.
    viewer = PdfViewer(session)

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_document_search_finds_known_text(tmp_path):
    path = tmp_path / "search.pdf"
    _make_pdf_with_text(path, ["nada de interessante aqui", "OpenFolio busca teste palavra achada aqui"])

    document = pdfium.PdfDocument(str(path))
    matches = DocumentSearch(document).find_all("achada")

    assert len(matches) == 1
    assert matches[0].page_index == 1


def test_document_search_returns_empty_for_missing_text(tmp_path):
    path = tmp_path / "search.pdf"
    _make_pdf_with_text(path, ["texto qualquer"])

    document = pdfium.PdfDocument(str(path))
    matches = DocumentSearch(document).find_all("inexistente")

    assert matches == []
