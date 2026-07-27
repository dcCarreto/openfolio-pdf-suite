import pytest
from pypdf import PdfReader

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
