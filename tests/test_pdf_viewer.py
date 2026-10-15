"""Testes do visualizador de PDF (ui/viewer/pdf_viewer.py e ui/viewer/search.py)."""

import ctypes
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.annotations import AddAnnotations, AnnotationSpec
from core.protect import ProtectPDF
from core.redaction import RedactionRect
from tests.conftest import HARD_PAGE_LAYOUTS
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.measure_state import MeasureState
from ui.redaction_state import RedactionState
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
    viewer = PdfViewer(DocumentSession(), AnnotationState(), RedactionState())
    assert viewer.content_stack.currentIndex() == 0


def test_viewer_loads_document_and_thumbnails(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    session.open(str(three_page_pdf))

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_zoom_in_increases_scale(three_page_pdf):
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
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
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_prompts_for_password_and_opens_on_correct_password(three_page_pdf, tmp_path, monkeypatch):
    _app()
    protected_path = tmp_path / "protected.pdf"
    ProtectPDF().run(str(three_page_pdf), str(protected_path), password="segredo123")

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *args, **kwargs: ("segredo123", True))
    )

    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    session.open(str(protected_path))

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_retries_password_prompt_after_wrong_password(three_page_pdf, tmp_path, monkeypatch):
    _app()
    protected_path = tmp_path / "protected.pdf"
    ProtectPDF().run(str(three_page_pdf), str(protected_path), password="segredo123")

    attempts = iter([("senha-errada", True), ("segredo123", True)])
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args, **kwargs: next(attempts)))

    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    session.open(str(protected_path))

    assert viewer.content_stack.currentIndex() == 1
    assert viewer.thumbnail_list.count() == 3


def test_viewer_handles_password_protected_pdf_without_crashing_when_user_cancels(
    three_page_pdf, tmp_path, monkeypatch
):
    _app()
    protected_path = tmp_path / "protected.pdf"
    ProtectPDF().run(str(three_page_pdf), str(protected_path), password="segredo123")

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args, **kwargs: ("", False)))

    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    session.open(str(protected_path))

    assert viewer.content_stack.currentIndex() == 0
    assert viewer._document is None


def test_viewer_shows_error_for_corrupted_pdf_without_prompting_password(tmp_path, monkeypatch):
    _app()
    garbage_path = tmp_path / "garbage.pdf"
    garbage_path.write_bytes(b"isto nao e um pdf de verdade")

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("nao deveria pedir senha para um PDF corrompido (nao criptografado)")

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(_fail_if_called))

    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())

    session.open(str(garbage_path))

    assert viewer.content_stack.currentIndex() == 0
    assert viewer._document is None


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
    viewer = PdfViewer(session, annotation_state, RedactionState())
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
    viewer = PdfViewer(session, annotation_state, RedactionState())
    session.open(str(path))
    annotation_state.set_tool("highlight")
    # set_page_active nunca foi chamado com True: equivale a uma ferramenta de marcação
    # selecionada, mas o usuário está numa aba diferente da de Anotações.

    viewer._on_canvas_pressed(10, 10)
    viewer._on_canvas_released(50, 20)

    assert annotation_state.pending() == []


def test_viewer_redaction_drag_creates_pending_rect(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    redaction_state = RedactionState()
    viewer = PdfViewer(session, AnnotationState(), redaction_state)
    session.open(str(path))
    redaction_state.set_page_active(True)

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    pending = redaction_state.pending()
    assert len(pending) == 1
    assert pending[0].page_index == 0
    assert pending[0].right > pending[0].left
    assert pending[0].top > pending[0].bottom


def test_viewer_ignores_canvas_clicks_when_redaction_page_not_active(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    redaction_state = RedactionState()
    viewer = PdfViewer(session, AnnotationState(), redaction_state)
    session.open(str(path))
    # set_page_active nunca foi chamado com True: equivale a estar em outra aba da sidebar.

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    assert redaction_state.pending() == []


def test_pending_redaction_changes_the_rendered_pixmap(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    redaction_state = RedactionState()
    viewer = PdfViewer(session, AnnotationState(), redaction_state)
    session.open(str(path))

    before = QPixmap(viewer._page_labels[0].pixmap())

    redaction_state.set_page_active(True)
    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    after = viewer._page_labels[0].pixmap()
    assert before.toImage() != after.toImage()


def test_viewer_measure_drag_sets_result(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    measure_state = MeasureState()
    viewer = PdfViewer(session, AnnotationState(), RedactionState(), measure_state)
    session.open(str(path))
    measure_state.set_page_active(True)

    scale = viewer._scale
    viewer._on_canvas_pressed(0, 0)
    viewer._on_canvas_released(72 * scale, 0)

    segment = measure_state.last_segment()
    assert segment is not None
    assert segment[0] == 0
    assert measure_state.last_distance_pt() == pytest.approx(72.0, abs=0.5)


def test_viewer_ignores_canvas_clicks_when_measure_page_not_active(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    measure_state = MeasureState()
    viewer = PdfViewer(session, AnnotationState(), RedactionState(), measure_state)
    session.open(str(path))
    # set_page_active nunca foi chamado com True: equivale a estar em outra aba da sidebar.

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    assert measure_state.last_segment() is None


def test_pending_measurement_changes_the_rendered_pixmap(tmp_path):
    _app()
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, ["conteúdo qualquer"])

    session = DocumentSession()
    measure_state = MeasureState()
    viewer = PdfViewer(session, AnnotationState(), RedactionState(), measure_state)
    session.open(str(path))

    before = QPixmap(viewer._page_labels[0].pixmap())

    measure_state.set_page_active(True)
    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_released(120, 80)

    after = viewer._page_labels[0].pixmap()
    assert before.toImage() != after.toImage()


def test_viewer_defaults_to_its_own_measure_state_when_none_given():
    _app()
    viewer = PdfViewer(DocumentSession(), AnnotationState(), RedactionState())
    assert isinstance(viewer.measure_state, MeasureState)


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


# -- coordenadas em páginas giradas / com CropBox (B01) ---------------------------------------


def _word_box_and_screen_corners(path, word: str, scale: float):
    """Caixa da palavra no espaço do usuário e onde seus cantos aparecem na tela, segundo o
    próprio pdfium (FPDF_PageToDevice) — independente da geometria do app."""
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        textpage = page.get_textpage()
        searcher = textpage.search(word)
        index, count = searcher.get_next()
        boxes = [textpage.get_charbox(i) for i in range(index, index + count)]
        searcher.close()
        textpage.close()
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        width, height = page.get_size()
        size_x, size_y = round(width * scale), round(height * scale)
        corners = []
        for x, y in ((box[0], box[1]), (box[2], box[3])):
            device_x, device_y = ctypes.c_int(), ctypes.c_int()
            pdfium_c.FPDF_PageToDevice(page, 0, 0, size_x, size_y, 0, x, y, device_x, device_y)
            corners.append((device_x.value, device_y.value))
    finally:
        document.close()
    (x0, y0), (x1, y1) = corners
    return box, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


@pytest.mark.parametrize(("name", "layout"), list(HARD_PAGE_LAYOUTS.items()))
def test_redaction_drag_marks_exactly_what_the_user_sees(make_text_pdf, name, layout):
    _app()
    path = make_text_pdf(f"{name}.pdf", [(80, 650, "CPF 123.456.789-09")], **layout)
    session = DocumentSession()
    redaction_state = RedactionState()
    viewer = PdfViewer(session, AnnotationState(), redaction_state)
    session.open(str(path))
    redaction_state.set_page_active(True)

    word_box, (sx0, sy0, sx1, sy1) = _word_box_and_screen_corners(path, "123.456.789-09", viewer._scale)
    viewer._on_canvas_pressed(sx0 - 3, sy0 - 3)
    viewer._on_canvas_released(sx1 + 3, sy1 + 3)

    (rect,) = redaction_state.pending()
    # A área arrastada na tela, convertida para o PDF, contém a palavra que estava sob ela.
    assert rect.left <= word_box[0] + 1 and rect.bottom <= word_box[1] + 1
    assert rect.right >= word_box[2] - 1 and rect.top >= word_box[3] - 1
    assert rect.right - rect.left < (word_box[2] - word_box[0]) + 20

    # E a marcação pendente é desenhada por cima da palavra (não em outro lugar).
    image = viewer._page_labels[0].pixmap().toImage()
    center = image.pixelColor((sx0 + sx1) // 2, (sy0 + sy1) // 2)
    assert center.lightness() < 90


@pytest.mark.parametrize("rotate", [90, 270])
def test_highlight_drag_on_rotated_page_marks_the_dragged_word(make_text_pdf, rotate):
    _app()
    path = make_text_pdf(f"rot{rotate}.pdf", [(80, 650, "palavra especial aqui")], rotate=rotate)
    session = DocumentSession()
    annotation_state = AnnotationState()
    viewer = PdfViewer(session, annotation_state, RedactionState())
    session.open(str(path))
    annotation_state.set_page_active(True)
    annotation_state.set_tool("highlight")

    word_box, (sx0, sy0, sx1, sy1) = _word_box_and_screen_corners(path, "especial", viewer._scale)
    # Arrasta do começo ao fim da palavra, como o usuário faria na tela: com /Rotate 90 o
    # texto desce pela tela; com 270, sobe.
    middle_x = (sx0 + sx1) / 2
    top_point, bottom_point = (middle_x, sy0 + 2), (middle_x, sy1 - 2)
    start, end = (top_point, bottom_point) if rotate == 90 else (bottom_point, top_point)
    viewer._on_canvas_pressed(*start)
    viewer._on_canvas_released(*end)

    (spec,) = annotation_state.pending()
    left = min(q[0] for q in spec.quads)
    right = max(q[2] for q in spec.quads)
    assert left == pytest.approx(word_box[0], abs=2)
    assert right == pytest.approx(word_box[2], abs=2)


def test_selecting_a_redaction_area_shows_its_page(three_page_pdf):
    _app()
    session = DocumentSession()
    redaction_state = RedactionState()
    viewer = PdfViewer(session, AnnotationState(), redaction_state)
    session.open(str(three_page_pdf))
    assert viewer._current_page == 0

    rect = RedactionRect(page_index=2, left=40, bottom=240, right=200, top=262)
    redaction_state.add_pending(rect)
    redaction_state.set_selected(rect)

    assert viewer._current_page == 2
