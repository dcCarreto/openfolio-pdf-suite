import pytest
from pypdf import PdfReader

from core.merge import MergePDF


def test_merge_concatenates_pages_in_order(make_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(200, 200), (200, 200)])
    pdf_b = make_pdf("b.pdf", [(300, 300)])
    output_path = tmp_path / "merged.pdf"

    MergePDF().run([str(pdf_a), str(pdf_b)], str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 3
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [200, 200, 300]


def test_merge_single_file_is_a_copy(make_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(200, 200)])
    output_path = tmp_path / "merged.pdf"

    MergePDF().run([str(pdf_a)], str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 1


def test_merge_with_empty_list_raises(tmp_path):
    output_path = tmp_path / "merged.pdf"

    with pytest.raises(ValueError):
        MergePDF().run([], str(output_path))
