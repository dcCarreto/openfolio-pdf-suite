"""Testes de fumaça: garantem que a janela principal é montada sem erros."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget

from ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_builds_with_all_sections():
    _app()
    window = MainWindow()

    assert window.windowTitle() == "OpenFolio PDF Suite"

    sidebar = window.findChild(QListWidget, "sidebar")
    assert sidebar is not None
    assert sidebar.count() == 5
    assert [sidebar.item(i).text() for i in range(sidebar.count())] == [
        "📄  Mesclar",
        "✂️  Dividir",
        "🔃  Páginas",
        "🗜️  Comprimir",
        "🖼️  Converter",
    ]
    assert window.stack.count() == 5

    window.close()


def test_main_window_has_menu_bar_and_status_bar():
    _app()
    window = MainWindow()

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles == ["Arquivo", "Ajuda"]
    assert window.statusBar().currentMessage() != ""

    window.close()
