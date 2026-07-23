from pypdf import PdfReader

from core.pages import RemovePages, ReorderPages, RotatePages


def test_rotate_all_pages_defaults_to_90_degrees(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200)])
    output_path = tmp_path / "rotated.pdf"

    RotatePages().run(str(pdf_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert [int(page.rotation) for page in reader.pages] == [90, 90]


def test_rotate_specific_pages_with_custom_angle(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200), (200, 200)])
    output_path = tmp_path / "rotated.pdf"

    RotatePages().run(str(pdf_path), str(output_path), angle=180, pages=[1])

    reader = PdfReader(str(output_path))
    assert [int(page.rotation) for page in reader.pages] == [0, 180, 0]


def test_reorder_pages(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])
    output_path = tmp_path / "reordered.pdf"

    ReorderPages().run(str(pdf_path), str(output_path), order=[2, 0, 1])

    reader = PdfReader(str(output_path))
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [300, 100, 200]


def test_remove_pages(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])
    output_path = tmp_path / "removed.pdf"

    RemovePages().run(str(pdf_path), str(output_path), pages=[1])

    reader = PdfReader(str(output_path))
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [100, 300]
