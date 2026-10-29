"""Testes de fumaça: garantem que a janela principal é montada sem erros."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.tools import DEFAULT_QUICK, TOOLS
from ui.viewer.pdf_viewer import PdfViewer


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_opens_on_home_with_all_tools_in_the_tools_tab():
    _app()
    window = MainWindow()

    assert window.windowTitle() == "OpenFolio PDF Suite"
    assert not window.windowIcon().isNull()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Início", "Ferramentas"]
    assert window.tabs.currentWidget() is window.home
    assert window.documents() == []  # nenhum documento até o usuário abrir um

    cards = window.tools_center.cards  # as 23 ferramentas, nos 8 grupos
    assert sorted(card.text() for card in cards.values()) == sorted(tool.title for tool in TOOLS.values())
    assert len(cards) == 23
    assert all(not card.icon().isNull() for card in cards.values())

    doc = window.current_document()  # uma aba de documento vazia, como uma janela sem PDF
    assert window.documents() == [doc] and window.tabs.currentWidget() is doc
    assert isinstance(window.viewer, PdfViewer)
    assert window.viewer.content_stack.currentIndex() == 0  # nenhum PDF aberto ainda
    assert window.session.path() is None
    assert window.stack.count() == 30 and not window.stack.isVisibleTo(doc)  # nenhuma ferramenta aberta
    assert list(doc._quick_buttons) == DEFAULT_QUICK
    assert window.annotation_state.is_page_active() is False

    window.close()


def test_opening_annotations_activates_annotation_state_and_closing_deactivates():
    _app()
    window = MainWindow()
    annotations_row = window._annotations_row

    window.open_tool(annotations_row)
    doc = window.document
    assert window.annotation_state.is_page_active() is True
    assert doc.current_panel().isVisibleTo(doc) and doc.current_panel().title_label.text() == "Anotações"
    assert doc._quick_buttons["AnnotationsPage"].isChecked()

    doc.close_tool()
    assert window.annotation_state.is_page_active() is False
    assert not doc.stack.isVisibleTo(doc)

    window.close()


def test_opening_redaction_deactivates_annotations():
    _app()
    window = MainWindow()
    redaction_row = window._redaction_row

    window.open_tool(redaction_row)
    assert window.redaction_state.is_page_active() is True
    assert window.annotation_state.is_page_active() is False

    window.open_tool(window._annotations_row)
    assert window.redaction_state.is_page_active() is False
    assert window.annotation_state.is_page_active() is True

    window.close()


def test_main_window_has_menu_bar_and_status_bar():
    _app()
    window = MainWindow()

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles == ["Arquivo", "Editar", "Exibir", "Ajuda"]
    # A promessa de privacidade fica sempre na barra de status.
    assert window._privacy_label.text() == "Local · nenhum arquivo sai deste computador"

    window.close()
