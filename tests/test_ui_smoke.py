"""Testes de fumaça: garantem que a janela principal é montada sem erros."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTabWidget

from ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_builds_with_three_tabs():
    _app()
    window = MainWindow()

    assert window.windowTitle() == "OpenFolio PDF Suite"
    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert tabs.count() == 3
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Mesclar", "Dividir", "Páginas"]

    window.close()
