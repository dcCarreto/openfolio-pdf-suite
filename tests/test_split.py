from pathlib import Path

import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.bookmarks import AddBookmarks
from core.split import SplitByBookmarks, SplitPDF


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


def test_split_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_dir = tmp_path / "out"

    with pytest.raises(EncryptedPDFError):
        SplitPDF().run(str(encrypted_path), str(output_dir))


def test_split_by_bookmarks_creates_one_file_per_top_level_bookmark(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 6)
    with_bookmarks = tmp_path / "with_bookmarks.pdf"
    AddBookmarks().run(str(pdf_path), str(with_bookmarks), bookmarks=[("Capítulo 1", 0), ("Capítulo 2", 3)])

    output_dir = tmp_path / "out"
    output_paths = SplitByBookmarks().run(str(with_bookmarks), str(output_dir))

    assert len(output_paths) == 2
    page_counts = [len(PdfReader(path).pages) for path in output_paths]
    assert page_counts == [3, 3]


def test_split_by_bookmarks_last_part_runs_to_end_of_document(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 5)
    with_bookmarks = tmp_path / "with_bookmarks.pdf"
    AddBookmarks().run(str(pdf_path), str(with_bookmarks), bookmarks=[("Intro", 0), ("Meio", 2)])

    output_dir = tmp_path / "out"
    output_paths = SplitByBookmarks().run(str(with_bookmarks), str(output_dir))

    page_counts = [len(PdfReader(path).pages) for path in output_paths]
    assert page_counts == [2, 3]


def test_split_by_bookmarks_sanitizes_titles_for_filenames(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 2)
    with_bookmarks = tmp_path / "with_bookmarks.pdf"
    AddBookmarks().run(str(pdf_path), str(with_bookmarks), bookmarks=[("Cap/ítulo: 1?", 0)])

    output_dir = tmp_path / "out"
    output_paths = SplitByBookmarks().run(str(with_bookmarks), str(output_dir))

    assert len(output_paths) == 1
    assert "/" not in Path(output_paths[0]).name.replace(str(output_dir), "")


def test_split_by_bookmarks_raises_without_bookmarks(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_dir = tmp_path / "out"

    with pytest.raises(ValueError):
        SplitByBookmarks().run(str(pdf_path), str(output_dir))


def test_split_by_bookmarks_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_dir = tmp_path / "out"

    with pytest.raises(EncryptedPDFError):
        SplitByBookmarks().run(str(encrypted_path), str(output_dir))
