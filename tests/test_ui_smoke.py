"""Testes de fumaça: garantem que a janela principal é montada sem erros."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget

from ui.main_window import MainWindow
from ui.viewer.pdf_viewer import PdfViewer


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_builds_with_all_sections():
    _app()
    window = MainWindow()

    assert window.windowTitle() == "OpenFolio PDF Suite"
    assert not window.windowIcon().isNull()

    sidebar = window.findChild(QListWidget, "sidebar")
    assert sidebar is not None
    assert sidebar.count() == 18
    assert [sidebar.item(i).text() for i in range(sidebar.count())] == [
        "Criar PDF",
        "Mesclar",
        "Dividir",
        "Páginas",
        "Comprimir",
        "Converter",
        "Marca d'água",
        "Proteger",
        "Metadados",
        "Numeração",
        "Extrair texto",
        "Extrair imagens",
        "Cortar/Redimensionar",
        "Marcadores",
        "Campos de formulário",
        "Anotações",
        "OCR",
        "Redigir/Sanitizar",
    ]
    assert all(not sidebar.item(i).icon().isNull() for i in range(sidebar.count()))
    assert window.stack.count() == 18

    assert isinstance(window.viewer, PdfViewer)
    assert window.viewer.content_stack.currentIndex() == 0  # nenhum PDF aberto ainda
    assert window.session.path() is None
    assert window.annotation_state.is_page_active() is False  # "Criar PDF" é a aba inicial

    window.close()


def test_selecting_annotations_row_activates_annotation_state():
    _app()
    window = MainWindow()
    annotations_row = window._annotations_row
    assert window.sidebar.item(annotations_row).text() == "Anotações"

    window.sidebar.setCurrentRow(annotations_row)
    assert window.annotation_state.is_page_active() is True

    window.sidebar.setCurrentRow(0)
    assert window.annotation_state.is_page_active() is False

    window.close()


def test_selecting_redaction_row_activates_redaction_state():
    _app()
    window = MainWindow()
    redaction_row = window._redaction_row
    assert window.sidebar.item(redaction_row).text() == "Redigir/Sanitizar"

    window.sidebar.setCurrentRow(redaction_row)
    assert window.redaction_state.is_page_active() is True
    assert window.annotation_state.is_page_active() is False

    window.sidebar.setCurrentRow(window._annotations_row)
    assert window.redaction_state.is_page_active() is False
    assert window.annotation_state.is_page_active() is True

    window.close()


def test_main_window_has_menu_bar_and_status_bar():
    _app()
    window = MainWindow()

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles == ["Arquivo", "Ajuda"]
    assert window.statusBar().currentMessage() != ""

    window.close()
