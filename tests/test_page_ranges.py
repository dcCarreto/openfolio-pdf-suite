"""Testes de ui/page_ranges.py e do uso de páginas contadas a partir de 1 na aba Páginas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from ui.document_session import DocumentSession
from ui.tasks import wait_for_tasks
from ui.page_ranges import parse_page_ranges
from ui.pages.pages_page import PagesPage
from ui.widgets.file_picker import FilePicker


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", [0]),
        ("1-3, 5", [0, 1, 2, 4]),
        (" 2 , 4 - 5 ", [1, 3, 4]),
        ("8-", [7, 8, 9]),
        ("4-1", [3, 2, 1, 0]),
        ("", []),
        ("1,,2,", [0, 1]),
    ],
)
def test_parse_page_ranges(text, expected):
    assert parse_page_ranges(text, total_pages=10) == expected


@pytest.mark.parametrize("text", ["0", "11", "3-12", "a", "1-2-3", "-3", "1.5"])
def test_parse_page_ranges_rejects_invalid_input(text):
    with pytest.raises(ValueError):
        parse_page_ranges(text, total_pages=10)


def test_open_ended_range_needs_the_page_count():
    with pytest.raises(ValueError):
        parse_page_ranges("3-")


class _Messages:
    def __init__(self, monkeypatch):
        self.shown: list[tuple[str, str]] = []
        for kind in ("information", "warning", "critical"):
            monkeypatch.setattr(
                QMessageBox,
                kind,
                lambda _parent, _title, text, _kind=kind: self.shown.append((_kind, text)),
            )


def _page_widths(path) -> list[int]:
    return [round(float(page.mediabox.width)) for page in PdfReader(str(path)).pages]


def test_pages_tab_counts_pages_from_one(make_pdf, tmp_path, monkeypatch):
    _app()
    messages = _Messages(monkeypatch)
    source = make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 300), (400, 300)])
    session = DocumentSession()
    session.open(str(source))
    page = PagesPage(session)
    page.operation_combo.setCurrentIndex(2)  # Remover
    page.remove_edit.setText("1, 3-")

    page._apply()
    wait_for_tasks()

    assert messages.shown[-1][0] == "information"
    assert _page_widths(session.path()) == [200]


def test_pages_tab_reorders_with_a_reversed_range(make_pdf, monkeypatch):
    _app()
    messages = _Messages(monkeypatch)
    source = make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 300)])
    session = DocumentSession()
    session.open(str(source))
    page = PagesPage(session)
    page.operation_combo.setCurrentIndex(1)  # Reordenar
    page.reorder_edit.setText("3-1")

    page._apply()
    wait_for_tasks()

    assert messages.shown[-1][0] == "information"
    assert _page_widths(session.path()) == [300, 200, 100]


def test_pages_tab_explains_a_page_that_does_not_exist(make_pdf, monkeypatch):
    _app()
    messages = _Messages(monkeypatch)
    source = make_pdf("doc.pdf", [(100, 300), (200, 300)])
    session = DocumentSession()
    session.open(str(source))
    page = PagesPage(session)
    page.operation_combo.setCurrentIndex(2)
    page.remove_edit.setText("3")

    page._apply()
    wait_for_tasks()

    kind, text = messages.shown[-1]
    assert kind == "warning" and "3" in text and "2 página" in text
    assert session.path() == str(source)  # nada foi gravado


def test_pages_tab_replaces_an_inclusive_range(make_pdf, monkeypatch):
    _app()
    messages = _Messages(monkeypatch)
    source = make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 300)])
    replacement = make_pdf("novas.pdf", [(900, 300)])
    session = DocumentSession()
    session.open(str(source))
    page = PagesPage(session)
    page.operation_combo.setCurrentIndex(4)  # Substituir
    monkeypatch.setattr(page.replace_source_picker, "path", lambda: str(replacement))
    page.replace_start_spin.setValue(2)
    page.replace_end_spin.setValue(3)

    page._apply()
    wait_for_tasks()

    assert messages.shown[-1][0] == "information"
    assert _page_widths(session.path()) == [100, 900]


def test_save_picker_suggests_a_new_file_and_follows_the_open_document(tmp_path):
    _app()
    first = tmp_path / "contrato.pdf"
    first.write_bytes(b"%PDF-1.4")
    (tmp_path / "contrato_editado.pdf").write_bytes(b"%PDF-1.4")
    second = tmp_path / "outro.pdf"
    session = DocumentSession()
    session.open(str(first))
    picker = FilePicker(mode="save", suggested_source=session.path)

    # Padrão: o resultado vai para o documento aberto, numa versão nova (Ctrl+Z desfaz).
    assert picker.applies_to_document()
    assert session.is_version_path(picker.path())

    picker._apply_to_document = False  # "salvar em outro arquivo"
    assert picker.path() == str(tmp_path / "contrato_editado (2).pdf")  # não sobrescreve

    picker._path = str(tmp_path / "escolhido.pdf")
    picker._path_source = session.source_path()
    assert picker.path() == str(tmp_path / "escolhido.pdf")

    session.open(str(second))  # outro documento: a escolha antiga não vale mais
    assert picker.path() == str(tmp_path / "outro_editado.pdf")
    assert picker.path_edit.text() == str(tmp_path / "outro_editado.pdf")


def test_format_page_ranges_groups_consecutive_pages():
    from ui.page_ranges import format_page_ranges

    assert format_page_ranges([0, 1, 2, 4, 7, 8]) == "1-3, 5, 8-9"
    assert format_page_ranges([]) == ""
    assert parse_page_ranges(format_page_ranges([3, 0, 1]), 5) == [0, 1, 3]


def test_thumbnail_selection_fills_the_pages_field(tmp_path):
    from pypdf import PdfWriter

    from ui.annotation_state import AnnotationState
    from ui.pages.pages_page import PagesPage
    from ui.redaction_state import RedactionState
    from ui.viewer.pdf_viewer import PdfViewer

    _app()
    path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=200, height=200)
    writer.write(str(path))
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    page = PagesPage(session)
    session.open(str(path))
    thumbnails = viewer.thumbnail_list

    for row in (0, 1, 3):
        thumbnails.item(row).setSelected(True)
    assert session.selected_pages() == [0, 1, 3]

    viewer._show_single_page(4)  # navegar não desfaz a seleção de várias páginas
    assert session.selected_pages() == [0, 1, 3]

    page.operation_combo.setCurrentIndex(2)  # Remover
    button = page._selection_buttons[1]  # o do campo "Páginas a remover"
    assert button.isEnabled()
    button.click()
    assert page.remove_edit.text() == "1-2, 4"


def test_current_page_button_uses_the_page_in_the_viewer(tmp_path):
    from pypdf import PdfWriter

    from ui.annotation_state import AnnotationState
    from ui.pages.bookmarks_page import BookmarksPage
    from ui.redaction_state import RedactionState
    from ui.viewer.pdf_viewer import PdfViewer

    _app()
    path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=200, height=200)
    writer.write(str(path))
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    page = BookmarksPage(session)
    session.open(str(path))
    viewer._show_single_page(3)

    button = next(b for b in page.findChildren(QPushButton) if b.text() == "Página atual")
    button.click()

    assert page.page_spin.value() == 4


def test_clicking_a_layer_chooses_it(tmp_path):
    from ui.pages.layers_page import LayersPage

    _app()
    page = LayersPage(DocumentSession())
    page._layer_indexes = [0, 1, 2]
    for name in ("a", "b", "c"):
        page.layers_list.addItem(name)

    page.layers_list.setCurrentRow(2)

    assert page.layer_index_spin.value() == 3
