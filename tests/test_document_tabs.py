"""A janela em abas: Início, Ferramentas e uma aba por documento."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.main_window import MainWindow
from ui.tasks import wait_for_tasks


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    # Fechar com alterações pergunta se salva: offscreen ninguém responderia.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()


def _pdf(path, pages=2, with_outline=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=300, height=300)
    if with_outline:
        writer.add_outline_item("Capítulo", 1)
    writer.write(str(path))
    return str(path)


def test_each_pdf_gets_a_tab_and_the_menus_follow_the_tab_in_front(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    first = window.open_document(_pdf(tmp_path / "um.pdf"))
    second = window.open_document(_pdf(tmp_path / "dois.pdf"))

    assert window.documents() == [first, second] and window.document is second
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Início", "Ferramentas", "um.pdf", "dois.pdf"]
    assert window.windowTitle() == "dois.pdf — OpenFolio PDF Suite"

    page = window.open_tool(window._row_of["WatermarkPage"])  # muda só o segundo
    page.text_edit.setText("RASCUNHO")
    page._apply()
    assert wait_for_tasks()
    # Na aba, o ponto no lugar do "x"; na barra do visualizador, o selo e "Salvar"; na de
    # status, quantas alterações faltam salvar. Nada de "*" no nome.
    assert window.tabs.tabText(3) == "dois.pdf" and second.close_button.is_dirty() and not first.close_button.is_dirty()
    assert "alterações não salvas" in second.close_button.accessibleName()
    assert window.windowTitle() == "dois.pdf — OpenFolio PDF Suite" and window._undo_action.isEnabled()
    assert second.state_badge.text().startswith("● ") and second.state_badge.property("state") == "unsaved"
    assert first.state_badge.text() == "✓ Salvo"
    assert window.doc_state_label.text() == "1 alteração aplicada, não salva"
    assert window.page_status_label.text().startswith("Página 1 de ")
    assert second.save_button.isEnabled() and not first.save_button.isEnabled()  # a barra segue cada documento
    assert first.print_button.isEnabled() and second.print_button.isEnabled()

    window.tabs.setCurrentWidget(first)
    assert window.windowTitle() == "um.pdf — OpenFolio PDF Suite"
    assert not window._undo_action.isEnabled() and not window._save_action.isEnabled()
    assert first.current_tool() == -1  # cada documento com as próprias ferramentas abertas


def test_closing_a_tab_with_changes_asks_and_the_last_one_goes_back_home(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    page = window.open_tool(window._row_of["WatermarkPage"])
    page.text_edit.setText("RASCUNHO")
    page._apply()
    assert wait_for_tasks() and doc.session.is_modified()

    asked = []

    def answer(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", answer)
    assert not window.close_document(doc)
    assert asked and "doc.pdf" in asked[0] and window.documents() == [doc]

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    assert window.close_document(doc)
    assert window.documents() == [] and window.tabs.currentWidget() is window.home


def test_an_open_pdf_comes_back_to_the_front_and_an_empty_tab_is_reused(window, tmp_path):
    empty = window.current_document()
    path = _pdf(tmp_path / "doc.pdf")

    assert window.open_document(path) is empty  # a aba vazia recebe o documento
    window.tabs.setCurrentWidget(window.home)
    assert window.open_document(path) is empty and window.document is empty
    assert len(window.documents()) == 1


def test_the_viewer_open_button_opens_another_tab(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    first = window.open_document(_pdf(tmp_path / "um.pdf"))
    second_path = _pdf(tmp_path / "dois.pdf")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (second_path, "PDF (*.pdf)"))

    first.viewer._browse_open()

    assert len(window.documents()) == 2 and first.session.source_path().endswith("um.pdf")
    assert window.document.session.source_path() == second_path


def test_left_rail_shows_and_hides_the_side_panel(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf", with_outline=True))
    window.show()
    QApplication.processEvents()
    side_panel = doc.viewer.side_panel
    thumbnails, bookmarks, attachments = doc._left_buttons

    assert side_panel.isVisible() and thumbnails.isChecked()
    assert bookmarks.isVisibleTo(doc) and not attachments.isVisibleTo(doc)  # sem anexos, sem botão

    bookmarks.click()
    assert side_panel.currentIndex() == 1 and bookmarks.isChecked() and not thumbnails.isChecked()
    bookmarks.click()  # o botão aberto recolhe o painel
    assert not side_panel.isVisible() and not bookmarks.isChecked()


def test_quick_tool_opens_and_a_second_click_closes_it(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    row = window._row_of["CompressPage"]
    button = doc._quick_buttons["CompressPage"]

    button.click()
    assert doc.current_tool() == row and doc.stack.isVisibleTo(doc)
    button.click()
    assert doc.current_tool() == -1 and not doc.stack.isVisibleTo(doc)

    doc.all_tools_button.click()
    assert window.tabs.currentWidget() is window.tools_center
    window.tools_center.cards["CompressPage"].click()
    assert window.document is doc and doc.current_tool() == row and window.tabs.currentWidget() is doc
