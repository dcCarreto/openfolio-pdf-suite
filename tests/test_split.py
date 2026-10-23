from pathlib import Path

import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError, add_object
from core.bookmarks import AddBookmarks
from core.split import SplitAtBlankPages, SplitByBookmarks, SplitByRanges, SplitBySize, SplitPDF


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


def test_split_by_bookmarks_keeps_pages_before_the_first_bookmark(make_pdf, tmp_path):
    # Capa e sumário (antes do primeiro marcador) sumiam da saída.
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 6)
    with_bookmarks = tmp_path / "with_bookmarks.pdf"
    AddBookmarks().run(str(pdf_path), str(with_bookmarks), bookmarks=[("Cap 1", 2), ("Cap 2", 4)])

    output_paths = SplitByBookmarks().run(str(with_bookmarks), str(tmp_path / "out"))

    assert [len(PdfReader(path).pages) for path in output_paths] == [2, 2, 2]
    assert Path(output_paths[0]).name == "with_bookmarks_00_inicio.pdf"


def test_split_names_sort_in_document_order(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 11)

    output_paths = SplitPDF().run(str(pdf_path), str(tmp_path / "out"))

    names = [Path(path).name for path in output_paths]
    assert names[0] == "doc_part01.pdf" and names[-1] == "doc_part11.pdf"
    assert sorted(names) == names


def _widths(path):
    return [int(page.mediabox.width) for page in PdfReader(path).pages]


def _bulky_pdf(path, count, payload=20_000):
    """Páginas de larguras 101, 102... com um fluxo de conteúdo de ~`payload` bytes cada
    (um comentário de PDF: não desenha nada, mas pesa)."""
    import os

    from pypdf import PdfWriter
    from pypdf.generic import NameObject, StreamObject

    writer = PdfWriter()
    for index in range(count):
        page = writer.add_blank_page(width=101 + index, height=200)
        stream = StreamObject()
        stream.set_data(b"%" + os.urandom(payload // 2).hex().encode() + b"\n")
        page[NameObject("/Contents")] = add_object(writer, stream)
    writer.write(str(path))
    return path


def test_split_by_ranges_writes_one_file_per_group(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(101 + i, 200) for i in range(6)])

    output_paths = SplitByRanges().run(str(pdf_path), str(tmp_path / "out"), [[0, 1, 2, 4], [5], []])

    assert [_widths(path) for path in output_paths] == [[101, 102, 103, 105], [106]]
    with pytest.raises(ValueError, match="6 página"):
        SplitByRanges().run(str(pdf_path), str(tmp_path / "out"), [[6]])


def test_split_by_size_keeps_every_part_under_the_limit_and_the_pages_in_order(tmp_path):
    pdf_path = _bulky_pdf(tmp_path / "doc.pdf", 10)
    limit = 70_000  # cabem três páginas de ~20 KB por parte

    output_paths = SplitBySize().run(str(pdf_path), str(tmp_path / "out"), limit)

    assert all(Path(path).stat().st_size <= limit for path in output_paths)
    assert [width for path in output_paths for width in _widths(path)] == list(range(101, 111))
    assert [len(_widths(path)) for path in output_paths] == [3, 3, 3, 1]


def test_a_page_bigger_than_the_limit_goes_alone(tmp_path):
    pdf_path = _bulky_pdf(tmp_path / "doc.pdf", 3)

    output_paths = SplitBySize().run(str(pdf_path), str(tmp_path / "out"), 5_000)

    assert [_widths(path) for path in output_paths] == [[101], [102], [103]]


def test_split_at_blank_pages_drops_the_separators(make_text_pdf, tmp_path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for name in ("A", "", "B", "C", "", "", "D"):
        if name:
            writer.append(str(make_text_pdf(f"{name}.pdf", [(100, 700, f"Documento {name}")])))
        else:
            writer.add_blank_page(width=612, height=792)
    pdf_path = tmp_path / "lote.pdf"
    writer.write(str(pdf_path))

    output_paths = SplitAtBlankPages().run(str(pdf_path), str(tmp_path / "out"))

    texts = [[page.extract_text().strip() for page in PdfReader(path).pages] for path in output_paths]
    assert texts == [["Documento A"], ["Documento B", "Documento C"], ["Documento D"]]


def test_split_at_blank_pages_without_any_is_an_error(make_text_pdf, tmp_path):
    pdf_path = make_text_pdf("doc.pdf", [(100, 700, "Sem separador")])

    with pytest.raises(ValueError, match="Nenhuma página em branco"):
        SplitAtBlankPages().run(str(pdf_path), str(tmp_path / "out"))


def test_split_page_ranges_mode_uses_the_selected_thumbnails(make_pdf, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.document_session import DocumentSession
    from ui.pages.split_page import SplitPage
    from ui.tasks import wait_for_tasks

    QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    pdf_path = make_pdf("doc.pdf", [(101 + i, 200) for i in range(5)])
    session = DocumentSession()
    session.open(str(pdf_path))
    session.set_selected_pages([1, 2, 4])
    page = SplitPage(session)
    monkeypatch.setattr(page.output_picker, "path", lambda: str(tmp_path / "out"))

    page.mode_combo.setCurrentIndex(2)
    page.selection_button.click()
    assert page.ranges_edit.text() == "2-3, 5"
    page.ranges_edit.setText(page.ranges_edit.text() + "; 1-")
    page._split_by_ranges()
    assert wait_for_tasks()

    output_dir = tmp_path / "out"
    assert [_widths(str(path)) for path in sorted(output_dir.iterdir())] == [[102, 103, 105], [101, 102, 103, 104, 105]]
    assert shown == ["PDF dividido em 2 arquivo(s)."]
