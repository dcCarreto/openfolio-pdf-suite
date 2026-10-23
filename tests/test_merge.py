import pytest
from pypdf import PdfReader, PdfWriter

from core.base import EncryptedPDFError
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


def test_merge_rejects_encrypted_input(make_pdf, make_encrypted_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(200, 200)])
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_path = tmp_path / "merged.pdf"

    with pytest.raises(EncryptedPDFError):
        MergePDF().run([str(pdf_a), str(encrypted_path)], str(output_path))


def _widths(path):
    return [int(page.mediabox.width) for page in PdfReader(str(path)).pages]


def _with_bookmark(make_pdf, name, sizes, title):
    path = make_pdf(name, sizes)
    writer = PdfWriter(clone_from=str(path))
    writer.add_outline_item(title, 0)
    writer.write(str(path))
    return path


def test_merge_takes_the_chosen_pages_of_each_file_in_the_given_order(make_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(101, 200), (102, 200), (103, 200)])
    pdf_b = make_pdf("b.pdf", [(201, 200), (202, 200)])
    output_path = tmp_path / "merged.pdf"

    MergePDF().run([str(pdf_a), str(pdf_b)], str(output_path), pages=[[2, 0], None])

    assert _widths(output_path) == [103, 101, 201, 202]


def test_merge_rejects_pages_outside_the_file(make_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(200, 200)])

    with pytest.raises(ValueError, match="a.pdf tem 1"):
        MergePDF().run([str(pdf_a)], str(tmp_path / "m.pdf"), pages=[[3]])


def test_one_bookmark_per_file_keeps_the_file_bookmarks_inside(make_pdf, tmp_path):
    pdf_a = _with_bookmark(make_pdf, "contrato.pdf", [(101, 200), (102, 200)], "Cláusulas")
    pdf_b = make_pdf("anexo.pdf", [(201, 200)])
    output_path = tmp_path / "merged.pdf"

    MergePDF().run([str(pdf_a), str(pdf_b)], str(output_path), bookmark_per_file=True)

    reader = PdfReader(str(output_path))
    outline = reader.outline
    assert [item.title for item in outline if not isinstance(item, list)] == ["contrato", "anexo"]
    assert [item.title for item in outline[1]] == ["Cláusulas"]  # dentro do "contrato"
    assert reader.get_destination_page_number(outline[2]) == 2  # o anexo começa na página 3


def test_interleave_alternates_fronts_and_backs_and_can_read_the_backs_reversed(make_pdf, tmp_path):
    fronts = make_pdf("frentes.pdf", [(101, 200), (103, 200), (105, 200)])
    backs = make_pdf("versos.pdf", [(106, 200), (104, 200), (102, 200)])  # o maço virado
    output_path = tmp_path / "merged.pdf"

    MergePDF().run([str(fronts), str(backs)], str(output_path), interleave=True, reverse_second=True)
    assert _widths(output_path) == [101, 102, 103, 104, 105, 106]

    MergePDF().run([str(fronts), str(backs)], str(output_path), interleave=True, pages=[None, [0]])
    assert _widths(output_path) == [101, 106, 103, 105]  # o que sobra das frentes vai no fim


def test_interleave_needs_exactly_two_files(make_pdf, tmp_path):
    pdf_a = make_pdf("a.pdf", [(200, 200)])

    with pytest.raises(ValueError, match="dois arquivos"):
        MergePDF().run([str(pdf_a)] * 3, str(tmp_path / "m.pdf"), interleave=True)


def test_merge_page_uses_the_pages_typed_for_each_file(make_pdf, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.document_session import DocumentSession
    from ui.pages.merge_page import MergePage
    from ui.tasks import wait_for_tasks
    from ui.widget_state import capture_state, restore_state

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    pdf_a = make_pdf("a.pdf", [(101, 200), (102, 200), (103, 200)])
    pdf_b = make_pdf("b.pdf", [(201, 200), (202, 200)])
    output_path = tmp_path / "merged.pdf"
    page = MergePage(DocumentSession())
    editor = page.file_list_editor
    editor.add_path(str(pdf_a))
    editor.add_path(str(pdf_b))
    editor.list_widget.setCurrentRow(0)
    editor.pages_edit.setText("2-")
    editor.pages_edit.textEdited.emit("2-")
    assert editor.list_widget.item(0).text() == f"{pdf_a}  [2-]"

    # A troca de idioma reconstrói a aba: as páginas de cada arquivo voltam.
    rebuilt = MergePage(DocumentSession())
    restore_state(rebuilt, capture_state(page))
    assert rebuilt.file_list_editor.entries() == [(str(pdf_a), "2-"), (str(pdf_b), "")]

    monkeypatch.setattr(rebuilt.output_picker, "path", lambda: str(output_path))
    rebuilt.bookmark_check.setChecked(True)
    rebuilt._merge()
    assert wait_for_tasks()

    assert _widths(output_path) == [102, 103, 201, 202]
    assert [item.title for item in PdfReader(str(output_path)).outline] == ["a", "b"]
