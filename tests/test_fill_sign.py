"""Preencher e assinar (A04): FillAndSign, o bloco de assinatura e a aba."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import QDate, QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core.fill_sign import FillAndSign, FillItem
from ui import preferences as preferences_module
from ui.document_session import DocumentSession
from ui.pages.fill_sign_page import FillSignPage, SignaturePad
from ui.tasks import wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _signature_png() -> bytes:
    _app()
    pad = SignaturePad()
    pad.add_stroke([QPointF(10, 50), QPointF(60, 10), QPointF(120, 60)])
    return pad.to_png()


def _text(path, page_index: int) -> str:
    document = pdfium.PdfDocument(str(path))
    try:
        return document[page_index].get_textpage().get_text_range()
    finally:
        document.close()


def _image_count(path, page_index: int) -> int:
    return len(PdfReader(str(path)).pages[page_index].images)


def test_fill_and_sign_draws_text_and_images_into_the_page(make_pdf, tmp_path):
    source = make_pdf("doc.pdf", [(400, 300), (400, 300)])
    writer = PdfWriter(clone_from=str(source))
    writer.pages[1].rotate(90)
    writer.write(str(source))
    output = tmp_path / "assinado.pdf"

    FillAndSign().run(
        str(source),
        str(output),
        [
            FillItem(0, (50, 200, 250, 230), text="José da Silva"),
            FillItem(0, (50, 100, 250, 180), image=_signature_png()),
            FillItem(1, (50, 50, 80, 200), text="18/10/2026"),
        ],
    )

    assert "José da Silva" in _text(output, 0)
    assert _image_count(output, 0) == 1
    assert "18/10/2026" in _text(output, 1)
    assert not PdfReader(str(output)).pages[0].annotations  # entra no conteúdo, não em anotações


def test_fill_and_sign_rejects_empty_items_and_missing_pages(make_pdf, tmp_path):
    source = make_pdf("doc.pdf", [(400, 300)])
    with pytest.raises(ValueError, match="pelo menos uma área"):
        FillAndSign().run(str(source), str(tmp_path / "x.pdf"), [FillItem(0, (0, 0, 10, 10), text="  ")])
    with pytest.raises(ValueError):
        FillAndSign().run(str(source), str(tmp_path / "x.pdf"), [FillItem(3, (0, 0, 10, 10), text="a")])


def test_signature_pad_exports_a_transparent_png_of_the_strokes():
    _app()
    pad = SignaturePad()
    assert pad.is_empty() and pad.to_png() == b""

    image = QImage.fromData(_signature_png())
    assert not image.isNull()
    assert image.hasAlphaChannel() and image.pixelColor(0, 0).alpha() == 0


@pytest.fixture
def page(make_pdf, monkeypatch):
    _app()
    monkeypatch.setattr(preferences_module, "_current", preferences_module.Preferences())
    session = DocumentSession()
    session.open(str(make_pdf("doc.pdf", [(400, 300), (400, 300)])))
    page = FillSignPage(session)
    page.area_pick_state.set_active_page(page)
    return page


def _pick(page, page_index=0, rect=(50, 50, 200, 80)):
    page.area_pick_state.pick(page_index, rect)


def test_each_dragged_area_gets_the_chosen_item(page):
    page.text_edit.setText("Ana")
    _pick(page)
    page.kind_combo.setCurrentIndex(1)  # Data
    page.date_edit.setDate(QDate(2026, 10, 18))
    _pick(page, 1)

    assert [(item.page_index, item.text) for item in page.items()] == [(0, "Ana"), (1, "18/10/2026")]
    assert page.items_list.item(1).text() == "Página 2 · 18/10/2026"
    assert page.area_pick_state.areas() == [(0, (50, 50, 200, 80)), (1, (50, 50, 200, 80))]

    page.remove_selected()
    assert [item.text for item in page.items()] == ["Ana"]


def test_text_and_signature_need_content_before_marking(page):
    _pick(page)
    assert not page.items() and "Digite o texto" in page.status_label.text()

    page.kind_combo.setCurrentIndex(2)  # Assinatura
    _pick(page)
    assert not page.items() and "Desenhe ou escolha" in page.status_label.text()

    assert page.store_image(2, _signature_png())
    assert not page.store_image(2, b"nada")
    _pick(page)
    assert page.items()[0].image == preferences_module.preferences().saved_image("signature")


def test_apply_creates_an_undoable_version_and_clears_the_list(page):
    session = page.session
    original = session.path()
    page.text_edit.setText("Ana")
    _pick(page)
    page.apply_button.click()

    assert wait_for_tasks()
    assert session.path() != original
    assert "Ana" in _text(session.path(), 0)
    assert not page.items() and not page.apply_button.isEnabled()
    session.undo()
    assert session.path() == original


def test_dragging_on_the_viewer_previews_the_item_at_its_real_size(page):
    from ui.annotation_state import AnnotationState
    from ui.redaction_state import RedactionState
    from ui.viewer.pdf_viewer import PdfViewer

    viewer = PdfViewer(page.session, AnnotationState(), RedactionState(), area_pick_state=page.area_pick_state)
    try:
        page.text_edit.setText("Ana")
        viewer._on_canvas_pressed(100, 100)
        viewer._on_canvas_moved(300, 140)
        # Durante o arrasto, a área já mostra o texto (pixels escuros dentro dela).
        image = viewer._page_labels[0].pixmap().toImage()
        ratio = image.devicePixelRatio()
        dark = sum(
            image.pixelColor(int(x * ratio), int(y * ratio)).lightness() < 100
            for x in range(105, 295, 2)
            for y in range(105, 138, 2)
        )
        assert dark > 0

        viewer._on_canvas_released(300, 140)
        assert [item.text for item in page.items()] == ["Ana"]
    finally:
        viewer.close_document()
