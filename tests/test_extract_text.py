import pytest

from core.base import EncryptedPDFError
from core.extract_text import ExtractText
from core.watermark import AddWatermark


def test_extract_text_returns_content_from_every_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300)])
    watermarked_path = tmp_path / "watermarked.pdf"
    AddWatermark().run(str(pdf_path), str(watermarked_path), text="OpenFolio")

    output_path = tmp_path / "out.txt"
    ExtractText().run(str(watermarked_path), str(output_path))

    content = output_path.read_text(encoding="utf-8")
    assert content.count("OpenFolio") == 2


def test_extract_text_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ExtractText().run(str(encrypted_path), str(tmp_path / "out.txt"))
