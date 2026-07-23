from pypdf import PdfReader

from core.compress import CompressPDF


def test_compress_preserves_page_count(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (300, 300)])
    output_path = tmp_path / "compressed.pdf"

    CompressPDF().run(str(pdf_path), str(output_path))

    assert output_path.exists()
    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2
