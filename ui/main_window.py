"""Janela principal da aplicação."""

from PySide6.QtWidgets import QMainWindow, QTabWidget

from ui.pages.merge_page import MergePage
from ui.pages.pages_page import PagesPage
from ui.pages.split_page import SplitPage


class MainWindow(QMainWindow):
    """Janela principal do OpenFolio PDF Suite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenFolio PDF Suite")
        self.resize(720, 480)

        tabs = QTabWidget()
        tabs.addTab(MergePage(), "Mesclar")
        tabs.addTab(SplitPage(), "Dividir")
        tabs.addTab(PagesPage(), "Páginas")
        self.setCentralWidget(tabs)
