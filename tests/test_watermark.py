import io

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.geometry import PageGeometry
from core.watermark import AddWatermark, watermark_preview


def _visual_text_box(path, page_index=0):
    """Retângulo do texto da página, no espaço visual, e o tamanho visual da página."""
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[page_index]
        geometry = PageGeometry.from_pdfium_page(page)
        textpage = page.get_textpage()
        boxes = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
        textpage.close()
    finally:
        document.close()
    user = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return geometry.user_rect_to_visual(user), (geometry.width, geometry.height)


def test_watermark_adds_text_to_every_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300)])
    output_path = tmp_path / "watermarked.pdf"

    AddWatermark().run(str(pdf_path), str(output_path), text="CONFIDENCIAL")

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2
    for page in reader.pages:
        assert "CONFIDENCIAL" in page.extract_text()


def test_watermark_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddWatermark().run(str(encrypted_path), str(tmp_path / "out.pdf"), text="X")


@pytest.mark.parametrize("rotate", [0, 90, 270])
def test_watermark_is_centered_on_the_page_as_seen(make_text_pdf, tmp_path, rotate):
    pdf_path = make_text_pdf(f"rot{rotate}.pdf", [], rotate=rotate)
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(pdf_path), str(output_path), text="CENTRO", rotation=0)

    (left, bottom, right, top), (width, height) = _visual_text_box(output_path)
    assert abs((left + right) / 2 - width / 2) < 5
    assert abs((bottom + top) / 2 - height / 2) < 30
    assert right - left > top - bottom  # com rotação 0, o texto corre na horizontal da tela


@pytest.mark.parametrize("rotate", [0, 90])
def test_corner_watermark_stays_inside_the_corner(make_text_pdf, tmp_path, rotate):
    pdf_path = make_text_pdf(f"rot{rotate}.pdf", [], rotate=rotate)
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(pdf_path), str(output_path), text="RASCUNHO", rotation=30, position="top-right")

    (left, bottom, right, top), (width, height) = _visual_text_box(output_path)
    assert width - 60 < right <= width - 30 and height - 60 < top <= height - 30
    assert left > width / 2 and bottom > height / 2


def test_tile_repeats_the_text_over_the_page(make_pdf, tmp_path):
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(make_pdf("doc.pdf", [(595, 842)])), str(output_path), text="COPIA", font_size=20, position="tile")

    assert PdfReader(str(output_path)).pages[0].extract_text().count("COPIA") >= 12


def test_only_the_chosen_pages_get_the_watermark(make_pdf, tmp_path):
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(make_pdf("doc.pdf", [(300, 300)] * 3)), str(output_path), text="VISTO", pages=[1])

    assert ["VISTO" in page.extract_text() for page in PdfReader(str(output_path)).pages] == [False, True, False]


@pytest.mark.parametrize("behind", [False, True])
def test_behind_puts_the_watermark_under_the_content(make_text_pdf, tmp_path, behind):
    pdf_path = make_text_pdf("doc.pdf", [(72, 400, "Conteudo")])
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(pdf_path), str(output_path), text="MARCA", behind=behind)

    text = PdfReader(str(output_path)).pages[0].extract_text()
    assert (text.index("MARCA") < text.index("Conteudo")) == behind  # o que vem antes é pintado embaixo


def test_color_and_opacity_are_applied(make_pdf, tmp_path):
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(
        str(make_pdf("doc.pdf", [(400, 200)])), str(output_path), text="XXXX", opacity=1, font_size=80, rotation=0, color="ff0000"
    )

    document = pdfium.PdfDocument(str(output_path))
    image = document[0].render().to_pil().convert("RGB")
    document.close()
    counts = {color: count for count, color in image.getcolors(1 << 24)}
    assert counts.get((255, 0, 0), 0) > 2000  # vermelho puro, sem transparência


def test_logo_is_stored_once_for_every_page(make_pdf, tmp_path):
    logo = tmp_path / "logo.png"
    Image.effect_noise((300, 300), 80).convert("RGBA").save(logo)  # ruído não comprime
    output_path = tmp_path / "out.pdf"

    AddWatermark().run(str(make_pdf("doc.pdf", [(595, 842)] * 10)), str(output_path), image_path=str(logo), position="bottom-right")

    reader = PdfReader(str(output_path))
    logos = {xobject.idnum for page in reader.pages for xobject in page["/Resources"]["/XObject"].values()}
    assert len(logos) == 1  # as dez páginas usam o mesmo objeto
    assert output_path.stat().st_size < 3 * logo.stat().st_size


def test_watermark_needs_text_or_an_image(make_pdf, tmp_path):
    with pytest.raises(ValueError, match="texto ou a imagem"):
        AddWatermark().run(str(make_pdf("doc.pdf", [(300, 300)])), str(tmp_path / "out.pdf"), text="  ")


def test_an_unreadable_image_is_reported(make_pdf, tmp_path):
    broken = tmp_path / "logo.png"
    broken.write_bytes(b"isto nao e uma imagem")

    with pytest.raises(ValueError, match="Não foi possível ler a imagem"):
        AddWatermark().run(str(make_pdf("doc.pdf", [(300, 300)])), str(tmp_path / "out.pdf"), image_path=str(broken))


def test_preview_is_the_one_page_with_the_watermark(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 300)])
    before = pdf_path.read_bytes()

    reader = PdfReader(io.BytesIO(watermark_preview(str(pdf_path), 1, text="PREVIA", behind=True)))

    assert len(reader.pages) == 1 and round(float(reader.pages[0].mediabox.width)) == 200
    assert "PREVIA" in reader.pages[0].extract_text()
    assert pdf_path.read_bytes() == before


def test_watermark_page_previews_and_applies_a_logo_to_the_selected_pages(make_pdf, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.document_session import DocumentSession
    from ui.pages.watermark_page import WatermarkPage
    from ui.tasks import wait_for_tasks

    QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    logo = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), "blue").save(logo)
    pdf_path = make_pdf("doc.pdf", [(300, 600)] * 3)
    session = DocumentSession()
    session.open(str(pdf_path))
    session.set_selected_pages([0, 2])
    page = WatermarkPage(session)
    output_path = tmp_path / "marcado.pdf"
    monkeypatch.setattr(page.output_picker, "path", lambda: str(output_path))
    monkeypatch.setattr(page.image_picker, "path", lambda: str(logo))

    page.kind_combo.setCurrentIndex(1)
    page.position_combo.setCurrentIndex(page.position_combo.findData("bottom-left"))
    page._preview()
    assert wait_for_tasks()
    preview = page.preview_label.pixmap()
    assert preview.deviceIndependentSize().toSize().height() == 320  # a página retrato inteira cabe
    assert not output_path.exists()

    page.selection_button.click()
    page._apply()
    assert wait_for_tasks()

    assert [bool(p.images) for p in PdfReader(str(output_path)).pages] == [True, False, True]
    assert shown == ["Marca d'água aplicada com sucesso."]
