import pytest
from pypdf import PdfReader

from core.split import SplitPDF


def test_split_default_is_one_page_per_file(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200), (200, 200)])
    output_dir = tmp_path / "out"

    output_paths = SplitPDF().run(str(pdf_path), str(output_dir))

    assert len(output_paths) == 3
    for path in output_paths:
        assert len(PdfReader(path).pages) == 1


def test_split_with_pages_per_file(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 5)
    output_dir = tmp_path / "out"

    output_paths = SplitPDF().run(str(pdf_path), str(output_dir), pages_per_file=2)

    assert len(output_paths) == 3
    page_counts = [len(PdfReader(path).pages) for path in output_paths]
    assert page_counts == [2, 2, 1]


def test_split_creates_output_dir(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_dir = tmp_path / "does" / "not" / "exist"

    output_paths = SplitPDF().run(str(pdf_path), str(output_dir))

    assert output_dir.exists()
    assert len(output_paths) == 1


def test_split_with_zero_or_negative_pages_per_file_raises(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_dir = tmp_path / "out"

    with pytest.raises(ValueError):
        SplitPDF().run(str(pdf_path), str(output_dir), pages_per_file=0)
    with pytest.raises(ValueError):
        SplitPDF().run(str(pdf_path), str(output_dir), pages_per_file=-1)
