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
