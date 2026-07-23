from pypdf import PdfReader

from core.page_numbers import AddPageNumbers


def test_add_page_numbers_starting_value(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300), (300, 300)])
    output_path = tmp_path / "numbered.pdf"

    AddPageNumbers().run(str(pdf_path), str(output_path), start_at=5)

    reader = PdfReader(str(output_path))
    texts = [page.extract_text() for page in reader.pages]
    assert "5" in texts[0]
    assert "6" in texts[1]
    assert "7" in texts[2]
