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
from ui.pages.bookmarks_page import BookmarksPage
from ui.pages.compress_page import CompressPage
from ui.pages.convert_page import ConvertPage
from ui.pages.create_page import CreatePage
from ui.pages.crop_page import CropPage
from ui.pages.extract_images_page import ExtractImagesPage
from ui.pages.extract_text_page import ExtractTextPage
from ui.pages.form_fields_page import FormFieldsPage
from ui.pages.merge_page import MergePage
from ui.pages.metadata_page import MetadataPage
from ui.pages.page_numbers_page import PageNumbersPage
from ui.pages.pages_page import PagesPage
from ui.pages.protect_page import ProtectPage
from ui.pages.split_page import SplitPage
from ui.pages.watermark_page import WatermarkPage
from ui.theme import apply_dark_titlebar
from ui.widgets.page_container import PageContainer

APP_VERSION = "0.1.0"

_SECTIONS = [
    ("🆕", "Criar PDF", "Crie um novo PDF em branco, com uma ou mais páginas.", CreatePage),
    ("📄", "Mesclar", "Combine vários PDFs em um único arquivo, na ordem que você escolher.", MergePage),
    ("✂️", "Dividir", "Separe um PDF em vários arquivos menores.", SplitPage),
    ("🔃", "Páginas", "Rotacione, reordene ou remova páginas de um PDF.", PagesPage),
    ("🗜️", "Comprimir", "Reduza o tamanho de um arquivo PDF.", CompressPage),
    (
        "🖼️",
        "Converter",
        "Converta entre PDF e imagens, documentos do Office (Word/Excel/PowerPoint) e XML.",
        ConvertPage,
    ),
    ("💧", "Marca d'água", "Adicione um texto de marca d'água sobre as páginas de um PDF.", WatermarkPage),
    ("🔒", "Proteger", "Proteja um PDF com senha, ou remova a senha de um PDF protegido.", ProtectPage),
    ("🏷️", "Metadados", "Edite título, autor, assunto e palavras-chave de um PDF.", MetadataPage),
    ("🔢", "Numeração", "Adicione números de página no rodapé de um PDF.", PageNumbersPage),
    ("📝", "Extrair texto", "Extraia todo o texto de um PDF para um arquivo .txt.", ExtractTextPage),
    ("📷", "Extrair imagens", "Extraia as imagens embutidas nas páginas de um PDF.", ExtractImagesPage),
    ("📐", "Cortar/Redimensionar", "Corte margens ou redimensione as páginas de um PDF.", CropPage),
    ("🔖", "Marcadores", "Monte um sumário de navegação (marcadores) para um PDF.", BookmarksPage),
    (
        "🧾",
        "Campos de formulário",
        "Adicione campos de formulário interativos (texto ou caixa de seleção) a um PDF.",
        FormFieldsPage,
    ),
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
