import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.crop import CropPages, ScalePages


def test_crop_reduces_mediabox(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "cropped.pdf"

    CropPages().run(str(pdf_path), str(output_path), left=10, bottom=10, right=10, top=10)

    reader = PdfReader(str(output_path))
    page = reader.pages[0]
    assert float(page.mediabox.width) == 180
    assert float(page.mediabox.height) == 180


def test_scale_resizes_pages(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "scaled.pdf"

    ScalePages().run(str(pdf_path), str(output_path), width=100, height=150)

    reader = PdfReader(str(output_path))
    page = reader.pages[0]
    assert round(float(page.mediabox.width)) == 100
    assert round(float(page.mediabox.height)) == 150


def test_crop_raises_when_margins_exceed_page_size(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "cropped.pdf"

    with pytest.raises(ValueError):
        CropPages().run(str(pdf_path), str(output_path), left=1000, right=1000)


def test_crop_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_path = tmp_path / "cropped.pdf"

    with pytest.raises(EncryptedPDFError):
        CropPages().run(str(encrypted_path), str(output_path), left=10)


def test_crop_margins_follow_the_page_as_seen_on_rotated_pages(make_text_pdf, tmp_path):
    import pypdfium2 as pdfium


    # Página 612x792 com /Rotate 90: na tela ela é 792 de largura por 612 de altura.
    pdf_path = make_text_pdf("rot.pdf", [(80, 650, "texto")], rotate=90)
    output_path = tmp_path / "cropped.pdf"

    CropPages().run(str(pdf_path), str(output_path), top=100)

    document = pdfium.PdfDocument(str(output_path))
    try:
        width, height = document[0].get_size()
    finally:
        document.close()
    assert (round(width), round(height)) == (792, 512)  # o "topo" cortado é o topo da tela


def test_scale_keeps_proportions_and_centers_the_content(tmp_path):
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas as rl_canvas

    # Quadrado de 100x100 no centro de uma página 200x200.
    pdf_path = tmp_path / "doc.pdf"
    canvas = rl_canvas.Canvas(str(pdf_path), pagesize=(200, 200))
    canvas.rect(50, 50, 100, 100, fill=1, stroke=0)
    canvas.save()
    output_path = tmp_path / "scaled.pdf"

    ScalePages().run(str(pdf_path), str(output_path), width=100, height=150)

    document = pdfium.PdfDocument(str(output_path))
    try:
        image = document[0].render(scale=2).to_pil().convert("L")
    finally:
        document.close()
    left, top, right, bottom = image.point(lambda value: 255 if value < 128 else 0).getbbox()
    # Reduzido por igual (continua quadrado, 50x50 pt = 100x100 px) e centralizado na
    # página nova de 100x150 pt, em vez de esticado para preencher a altura.
    assert abs((right - left) - 100) <= 2 and abs((bottom - top) - 100) <= 2
    assert abs((left + right) / 2 - image.width / 2) <= 2
    assert abs((top + bottom) / 2 - image.height / 2) <= 2
