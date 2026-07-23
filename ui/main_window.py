"""Janela principal da aplicação."""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from ui.icon import build_app_icon
from ui.pages.compress_page import CompressPage
from ui.pages.convert_page import ConvertPage
from ui.pages.merge_page import MergePage
from ui.pages.pages_page import PagesPage
from ui.pages.split_page import SplitPage
from ui.theme import apply_dark_titlebar
from ui.widgets.page_container import PageContainer

APP_VERSION = "0.1.0"

_SECTIONS = [
    ("📄", "Mesclar", "Combine vários PDFs em um único arquivo, na ordem que você escolher.", MergePage),
    ("✂️", "Dividir", "Separe um PDF em vários arquivos menores.", SplitPage),
    ("🔃", "Páginas", "Rotacione, reordene ou remova páginas de um PDF.", PagesPage),
    ("🗜️", "Comprimir", "Reduza o tamanho de um arquivo PDF.", CompressPage),
    ("🖼️", "Converter", "Converta entre páginas de PDF e imagens.", ConvertPage),
]


class MainWindow(QMainWindow):
    """Janela principal do OpenFolio PDF Suite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenFolio PDF Suite")
        self.setWindowIcon(build_app_icon())
        self.resize(900, 580)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)

        self.stack = QStackedWidget()

        for icon, name, subtitle, page_class in _SECTIONS:
            self.sidebar.addItem(QListWidgetItem(f"{icon}  {name}"))
            self.stack.addWidget(PageContainer(name, subtitle, page_class()))

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_menu_bar()
        self.statusBar().showMessage(f"OpenFolio PDF Suite {APP_VERSION}")

        apply_dark_titlebar(self)

    def _build_menu_bar(self):
        file_menu = self.menuBar().addMenu("Arquivo")
        quit_action = file_menu.addAction("Sair")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        help_menu = self.menuBar().addMenu("Ajuda")
        about_action = help_menu.addAction("Sobre o OpenFolio PDF Suite")
        about_action.triggered.connect(self._show_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "Sobre o OpenFolio PDF Suite",
            f"<b>OpenFolio PDF Suite</b> — versão {APP_VERSION}<br><br>"
            "Suite completa e open source de manipulação de PDF, 100% local, sem paywall.",
        )
