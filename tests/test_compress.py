from pypdf import PdfReader

from core.compress import CompressPDF
from core.watermark import AddWatermark


def test_compress_preserves_page_count(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (300, 300)])
    output_path = tmp_path / "compressed.pdf"

    CompressPDF().run(str(pdf_path), str(output_path))

    assert output_path.exists()
    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2


def test_compress_page_with_real_content_stream(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300)])
    watermarked_path = tmp_path / "watermarked.pdf"
    AddWatermark().run(str(pdf_path), str(watermarked_path), text="OpenFolio")

    output_path = tmp_path / "compressed.pdf"
    CompressPDF().run(str(watermarked_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2
    assert "OpenFolio" in reader.pages[0].extract_text()
