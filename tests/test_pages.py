import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.pages import InsertPages, RemovePages, ReorderPages, ReplacePages, RotatePages


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


def test_reorder_pages_rejects_out_of_range_index(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 100), (200, 200)])
    output_path = tmp_path / "reordered.pdf"

    with pytest.raises(ValueError):
        ReorderPages().run(str(pdf_path), str(output_path), order=[0, 5])


def test_remove_pages(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])
    output_path = tmp_path / "removed.pdf"

    RemovePages().run(str(pdf_path), str(output_path), pages=[1])

    reader = PdfReader(str(output_path))
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [100, 300]


def test_remove_all_pages_raises(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(100, 100), (200, 200)])
    output_path = tmp_path / "removed.pdf"

    with pytest.raises(ValueError):
        RemovePages().run(str(pdf_path), str(output_path), pages=[0, 1])


def test_rotate_pages_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_path = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        RotatePages().run(str(encrypted_path), str(output_path))


def test_insert_pages_in_the_middle(make_pdf, tmp_path):
    base_path = make_pdf("base.pdf", [(100, 100), (200, 200)])
    insert_path = make_pdf("insert.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    InsertPages().run(str(base_path), str(output_path), str(insert_path), at_index=1)

    reader = PdfReader(str(output_path))
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [100, 300, 200]


def test_insert_pages_at_start_and_end(make_pdf, tmp_path):
    base_path = make_pdf("base.pdf", [(100, 100)])
    insert_path = make_pdf("insert.pdf", [(300, 300)])

    start_out = tmp_path / "start.pdf"
    InsertPages().run(str(base_path), str(start_out), str(insert_path), at_index=0)
    assert [int(p.mediabox.width) for p in PdfReader(str(start_out)).pages] == [300, 100]

    end_out = tmp_path / "end.pdf"
    InsertPages().run(str(base_path), str(end_out), str(insert_path), at_index=1)
    assert [int(p.mediabox.width) for p in PdfReader(str(end_out)).pages] == [100, 300]


def test_insert_pages_rejects_out_of_range_index(make_pdf, tmp_path):
    base_path = make_pdf("base.pdf", [(100, 100)])
    insert_path = make_pdf("insert.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        InsertPages().run(str(base_path), str(tmp_path / "out.pdf"), str(insert_path), at_index=5)


def test_insert_pages_rejects_encrypted_input(make_encrypted_pdf, make_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    insert_path = make_pdf("insert.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        InsertPages().run(str(encrypted_path), str(tmp_path / "out.pdf"), str(insert_path), at_index=0)


def test_replace_pages_middle_range(make_pdf, tmp_path):
    base_path = make_pdf("base.pdf", [(100, 100), (150, 150), (200, 200), (250, 250)])
    replacement_path = make_pdf("replacement.pdf", [(300, 300), (300, 300)])
    output_path = tmp_path / "out.pdf"

    ReplacePages().run(
        str(base_path), str(output_path), str(replacement_path), start_index=1, end_index=3
    )

    reader = PdfReader(str(output_path))
    widths = [int(page.mediabox.width) for page in reader.pages]
    assert widths == [100, 300, 300, 250]


def test_replace_pages_rejects_invalid_range(make_pdf, tmp_path):
    base_path = make_pdf("base.pdf", [(100, 100), (200, 200)])
    replacement_path = make_pdf("replacement.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        ReplacePages().run(
            str(base_path), str(tmp_path / "out.pdf"), str(replacement_path), start_index=1, end_index=1
        )
    with pytest.raises(ValueError):
        ReplacePages().run(
            str(base_path), str(tmp_path / "out.pdf"), str(replacement_path), start_index=0, end_index=10
        )


def test_replace_pages_rejects_encrypted_input(make_encrypted_pdf, make_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    replacement_path = make_pdf("replacement.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ReplacePages().run(
            str(encrypted_path), str(tmp_path / "out.pdf"), str(replacement_path), start_index=0, end_index=1
        )
