"""Visualizador sem travar nem perder o lugar: zoom e troca de modo na rolagem contínua,
páginas liberadas ao rolar, miniaturas sob demanda, busca incremental e telas com escala."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer
from ui.viewer.render import logical_size, render_page
from ui.viewer.search import DocumentSearch


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _process_events(rounds: int = 5) -> None:
    for _ in range(rounds):
        QApplication.processEvents()


@pytest.fixture
def long_pdf(tmp_path):
    path = tmp_path / "longo.pdf"
    canvas = rl_canvas.Canvas(str(path), pagesize=(300, 400))
    for number in range(1, 41):
        canvas.drawString(50, 350, f"Pagina {number}")
        if number in (7, 30):
            canvas.drawString(50, 300, "palavra rara")
        canvas.showPage()
    canvas.save()
    return path


def _viewer(path) -> PdfViewer:
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.resize(900, 700)
    viewer.show()
    session.open(str(path))
    _process_events()
    return viewer


def _go_continuous(viewer: PdfViewer) -> None:
    viewer.continuous_button.click()
    _process_events()


def test_zoom_in_continuous_mode_keeps_the_current_page(long_pdf):
    # Antes, aumentar o zoom na página 20 levava de volta à página 1.
    viewer = _viewer(long_pdf)
    _go_continuous(viewer)
    viewer._scroll_to_page(19)
    _process_events()
    assert viewer._current_page == 19

    viewer._zoom_in()
    _process_events()
    assert viewer._current_page == 19

    viewer._zoom_out()
    viewer._zoom_out()
    _process_events()
    assert viewer._current_page == 19


def test_switching_to_continuous_mode_stays_on_the_same_page(long_pdf):
    viewer = _viewer(long_pdf)
    viewer._show_single_page(25)

    _go_continuous(viewer)

    assert viewer._current_page == 25


def test_continuous_mode_releases_pages_far_from_the_screen(long_pdf):
    viewer = _viewer(long_pdf)
    _go_continuous(viewer)
    first_screen = set(viewer._rendered_pages)
    assert 0 in first_screen

    viewer._scroll_to_page(39)
    _process_events()

    assert 39 in viewer._rendered_pages
    assert 0 not in viewer._rendered_pages  # a imagem da primeira página foi descartada
    assert len(viewer._rendered_pages) < 40


def test_thumbnails_are_rendered_gradually(long_pdf):
    # Antes, abrir o documento renderizava as 40 miniaturas de uma vez, com a janela parada.
    viewer = _viewer(long_pdf)
    thumbnails = viewer.thumbnail_list
    assert thumbnails.count() == 40

    thumbnails.render_all()

    assert thumbnails.pending_count() == 0


def test_search_finds_matches_incrementally(long_pdf):
    viewer = _viewer(long_pdf)

    viewer._search_document("palavra rara")
    assert viewer.is_searching()
    for _ in range(200):
        if not viewer.is_searching():
            break
        _process_events(1)

    assert not viewer.is_searching()
    assert [match.page_index for match in viewer._matches] == [6, 29]
    assert viewer._current_page == 6  # pula para a primeira ocorrência
    assert viewer.search_bar.count_label.text() == "1 de 2"


def test_search_is_restarted_by_a_new_query_and_stopped_by_closing(long_pdf):
    viewer = _viewer(long_pdf)
    viewer._search_document("palavra rara")
    viewer._search_document("Pagina 40")
    while viewer.is_searching():
        _process_events(1)
    assert [match.page_index for match in viewer._matches] == [39]

    viewer._search_document("Pagina")
    viewer._close_search()
    assert not viewer.is_searching()
    assert viewer._matches == []


def test_document_search_iterates_page_by_page(long_pdf):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(long_pdf))
    try:
        pages = list(DocumentSearch(document).iter_pages("palavra rara"))
    finally:
        document.close()

    assert len(pages) == 40
    assert [index for index, matches in enumerate(pages) if matches] == [6, 29]


def test_render_page_uses_the_screen_pixel_ratio(long_pdf):
    # Em telas com escala de 200%, a página era renderizada com metade dos pixels e
    # ampliada pelo sistema: texto borrado.
    import pypdfium2 as pdfium

    _app()
    document = pdfium.PdfDocument(str(long_pdf))
    try:
        normal = render_page(document[0], 1.0, 1.0)
        sharp = render_page(document[0], 1.0, 2.0)
    finally:
        document.close()

    assert sharp.width() == 2 * normal.width()
    assert sharp.devicePixelRatio() == 2.0
    assert logical_size(sharp) == logical_size(normal)
