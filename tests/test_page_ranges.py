"""Testes de ui/page_ranges.py e do uso de páginas contadas a partir de 1 na aba Páginas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication

from ui.document_session import DocumentSession
from ui.tasks import wait_for_tasks
from ui.page_ranges import parse_page_ranges
from ui.pages import pages_page
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
                pages_page.QMessageBox,
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

    assert picker.path() == str(tmp_path / "contrato_editado (2).pdf")  # não sobrescreve

    picker._path = str(tmp_path / "escolhido.pdf")
    picker._path_source = session.path()
    assert picker.path() == str(tmp_path / "escolhido.pdf")

    session.open(str(second))  # outro documento: a escolha antiga não vale mais
    assert picker.path() == str(tmp_path / "outro_editado.pdf")
    assert picker.path_edit.text() == str(tmp_path / "outro_editado.pdf")
