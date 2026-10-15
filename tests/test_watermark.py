import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.watermark import AddWatermark


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
    import pypdfium2 as pdfium

    from core.geometry import PageGeometry

    pdf_path = make_text_pdf(f"rot{rotate}.pdf", [], rotate=rotate)
    output_path = tmp_path / "out.pdf"
    AddWatermark().run(str(pdf_path), str(output_path), text="CENTRO", rotation=0)

    document = pdfium.PdfDocument(str(output_path))
    try:
        page = document[0]
        geometry = PageGeometry.from_pdfium_page(page)
        textpage = page.get_textpage()
        boxes = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
        textpage.close()
    finally:
        document.close()
    user = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    left, bottom, right, top = geometry.user_rect_to_visual(user)
    assert abs((left + right) / 2 - geometry.width / 2) < 5
    assert abs((bottom + top) / 2 - geometry.height / 2) < 30
    assert right - left > top - bottom  # com rotação 0, o texto corre na horizontal da tela
