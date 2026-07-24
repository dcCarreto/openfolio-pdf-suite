"""Janela principal da aplicação."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from ui import i18n
from ui.flags import build_br_flag_icon, build_us_flag_icon
from ui.i18n import tr
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


def _build_sections():
    return [
        ("🆕", tr("Criar PDF"), tr("Crie um novo PDF em branco, com uma ou mais páginas."), CreatePage),
        (
            "📄",
            tr("Mesclar"),
            tr("Combine vários PDFs em um único arquivo, na ordem que você escolher."),
            MergePage,
        ),
        ("✂️", tr("Dividir"), tr("Separe um PDF em vários arquivos menores."), SplitPage),
        ("🔃", tr("Páginas"), tr("Rotacione, reordene ou remova páginas de um PDF."), PagesPage),
        ("🗜️", tr("Comprimir"), tr("Reduza o tamanho de um arquivo PDF."), CompressPage),
        (
            "🖼️",
            tr("Converter"),
            tr("Converta entre PDF e imagens, documentos do Office (Word/Excel/PowerPoint) e XML."),
            ConvertPage,
        ),
        (
            "💧",
            tr("Marca d'água"),
            tr("Adicione um texto de marca d'água sobre as páginas de um PDF."),
            WatermarkPage,
        ),
        (
            "🔒",
            tr("Proteger"),
            tr("Proteja um PDF com senha, ou remova a senha de um PDF protegido."),
            ProtectPage,
        ),
        (
            "🏷️",
            tr("Metadados"),
            tr("Edite título, autor, assunto e palavras-chave de um PDF."),
            MetadataPage,
        ),
        (
            "🔢",
            tr("Numeração"),
            tr("Adicione números de página no rodapé de um PDF."),
            PageNumbersPage,
        ),
        (
            "📝",
            tr("Extrair texto"),
            tr("Extraia todo o texto de um PDF para um arquivo .txt."),
            ExtractTextPage,
        ),
        (
            "📷",
            tr("Extrair imagens"),
            tr("Extraia as imagens embutidas nas páginas de um PDF."),
            ExtractImagesPage,
        ),
        (
            "📐",
            tr("Cortar/Redimensionar"),
            tr("Corte margens ou redimensione as páginas de um PDF."),
            CropPage,
        ),
        (
            "🔖",
            tr("Marcadores"),
            tr("Monte um sumário de navegação (marcadores) para um PDF."),
            BookmarksPage,
        ),
        (
            "🧾",
            tr("Campos de formulário"),
            tr("Adicione campos de formulário interativos (texto ou caixa de seleção) a um PDF."),
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

        i18n.language_changed.changed.connect(self._on_language_changed)

        self._build_ui()
        apply_dark_titlebar(self)

    def _build_ui(self):
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)

        self.stack = QStackedWidget()

        for icon, name, subtitle, page_class in _build_sections():
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

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu(tr("Arquivo"))
        quit_action = file_menu.addAction(tr("Sair"))
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        help_menu = menu_bar.addMenu(tr("Ajuda"))
        about_action = help_menu.addAction(tr("Sobre o OpenFolio PDF Suite"))
        about_action.triggered.connect(self._show_about)

        # Mantemos uma referência Python (self._language_switcher): sem ela, o PySide6
        # pode coletar o widget mesmo com o Qt "dono" dele internamente via setCornerWidget.
        self._language_switcher = self._build_language_switcher()
        menu_bar.setCornerWidget(self._language_switcher, Qt.Corner.TopRightCorner)
        # Ao reconstruir o menu (troca de idioma), o widget do canto não fica visível
        # sozinho sem um show() explícito.
        self._language_switcher.show()

    def _build_language_switcher(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(4)

        icon_size = QSize(26, 17)

        us_button = QPushButton()
        us_button.setIcon(build_us_flag_icon())
        us_button.setIconSize(icon_size)
        us_button.setToolTip("English")
        us_button.setFixedSize(38, 26)
        us_button.setCursor(Qt.CursorShape.PointingHandCursor)
        us_button.clicked.connect(lambda: i18n.set_language(i18n.EN_US))

        br_button = QPushButton()
        br_button.setIcon(build_br_flag_icon())
        br_button.setIconSize(icon_size)
        br_button.setToolTip("Português (Brasil)")
        br_button.setFixedSize(38, 26)
        br_button.setCursor(Qt.CursorShape.PointingHandCursor)
        br_button.clicked.connect(lambda: i18n.set_language(i18n.PT_BR))

        layout.addWidget(us_button)
        layout.addWidget(br_button)
        return widget

    def _on_language_changed(self):
        current_row = self.sidebar.currentRow()

        # takeCentralWidget() desanexa o widget antigo imediatamente (ao contrário de
        # deleteLater(), que só agenda a remoção para o próximo ciclo do event loop),
        # evitando que ele continue aparecendo em buscas por objectName logo em seguida.
        old_central = self.takeCentralWidget()

        self._build_ui()

        if old_central is not None:
            old_central.deleteLater()
        if 0 <= current_row < self.sidebar.count():
            self.sidebar.setCurrentRow(current_row)

        apply_dark_titlebar(self)

    def _show_about(self):
        QMessageBox.about(
            self,
            tr("Sobre o OpenFolio PDF Suite"),
            tr(
                "<b>OpenFolio PDF Suite</b> — versão {version}<br><br>"
                "Suite completa e open source de manipulação de PDF, 100% local, sem paywall."
            ).format(version=APP_VERSION),
        )
