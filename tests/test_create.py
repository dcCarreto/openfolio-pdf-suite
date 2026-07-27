import pytest
from pypdf import PdfReader

from core.create import CreateBlankPDF


def test_create_blank_pdf_with_page_count_and_size(tmp_path):
    output_path = tmp_path / "new.pdf"

    CreateBlankPDF().run(str(output_path), page_count=3, width=300, height=400)

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 3
    assert float(reader.pages[0].mediabox.width) == 300
    assert float(reader.pages[0].mediabox.height) == 400


def test_create_blank_pdf_defaults_to_one_a4_page(tmp_path):
    output_path = tmp_path / "new.pdf"

    CreateBlankPDF().run(str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.width) == 595
    assert float(reader.pages[0].mediabox.height) == 842


def test_create_blank_pdf_with_zero_or_negative_page_count_raises(tmp_path):
    output_path = tmp_path / "new.pdf"

    with pytest.raises(ValueError):
        CreateBlankPDF().run(str(output_path), page_count=0)
    with pytest.raises(ValueError):
        CreateBlankPDF().run(str(output_path), page_count=-1)
