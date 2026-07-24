"""Testes do visualizador de PDF (ui/viewer/pdf_viewer.py e ui/viewer/search.py)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from core.annotations import AddAnnotations, AnnotationSpec
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.viewer.pdf_viewer import PdfViewer
from ui.viewer.render import render_page
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
    viewer = PdfViewer(DocumentSession(), AnnotationState())
    assert viewer.content_stack.currentIndex() == 0


def test_viewer_loads_document_and_thumbnails(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState())

    session.open(str(three_page_pdf))

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_zoom_in_increases_scale(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState())
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
    viewer = PdfViewer(session, AnnotationState())

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


def test_viewer_highlight_drag_creates_pending_annotation(tmp_path):
    _app()
    path = tmp_path / "highlight.pdf"
    _make_pdf_with_text(path, ["uma palavra especial chave aqui"])

    session = DocumentSession()
    annotation_state = AnnotationState()
    viewer = PdfViewer(session, annotation_state)
    session.open(str(path))
    annotation_state.set_page_active(True)
    annotation_state.set_tool("highlight")

    document = pdfium.PdfDocument(str(path))
    match = DocumentSearch(document).find_all("chave")[0]
    page_height = document[0].get_size()[1]
    scale = viewer._scale

    # Converte a posição conhecida da palavra (em coordenadas PDF) para pixels do widget,
    # o inverso do que PdfViewer._widget_point_to_pdf faz ao interpretar um arrasto real.
    x1, y1 = match.left * scale, (page_height - match.top) * scale
    x2, y2 = match.right * scale, (page_height - match.bottom) * scale

    viewer._on_canvas_pressed(x1, y1)
    viewer._on_canvas_released(x2, y2)

    pending = annotation_state.pending()
    assert len(pending) == 1
    assert pending[0].kind == "highlight"
    assert pending[0].page_index == 0
    assert pending[0].quads


def test_viewer_ignores_canvas_clicks_when_annotations_page_not_active(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    annotation_state = AnnotationState()
    viewer = PdfViewer(session, annotation_state)
    session.open(str(path))
    annotation_state.set_tool("highlight")
    # set_page_active nunca foi chamado com True: equivale a uma ferramenta de marcação
    # selecionada, mas o usuário está numa aba diferente da de Anotações.

    viewer._on_canvas_pressed(10, 10)
    viewer._on_canvas_released(50, 20)

    assert annotation_state.pending() == []


def test_saved_annotation_changes_the_rendered_pixmap(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf_with_text(path_in, ["conteúdo de teste"])
    path_out = tmp_path / "doc_annotated.pdf"

    before_doc = pdfium.PdfDocument(str(path_in))
    before = render_page(before_doc[0], 2.0)

    spec = AnnotationSpec(page_index=0, kind="highlight", color="ffeb3b", quads=[(40, 230, 200, 250)])
    AddAnnotations().run(str(path_in), str(path_out), [spec])

    after_doc = pdfium.PdfDocument(str(path_out))
    after = render_page(after_doc[0], 2.0)

    assert before.toImage() != after.toImage()
