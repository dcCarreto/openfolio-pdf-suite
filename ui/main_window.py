"""Janela principal da aplicação."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QWidget,
)

from ui import i18n
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.flags import build_br_flag_icon, build_us_flag_icon
from ui.i18n import tr
from ui.icon import build_app_icon
from ui.redaction_state import RedactionState
from ui.viewer.pdf_viewer import PdfViewer
from ui.sidebar_icons import (
    build_annotations_icon,
    build_bookmarks_icon,
    build_compress_icon,
    build_convert_icon,
    build_create_icon,
    build_crop_icon,
    build_extract_images_icon,
    build_extract_text_icon,
    build_form_fields_icon,
    build_merge_icon,
    build_metadata_icon,
    build_ocr_icon,
    build_page_numbers_icon,
    build_pages_icon,
    build_protect_icon,
    build_redaction_icon,
    build_signature_icon,
    build_split_icon,
    build_watermark_icon,
)
from ui.pages.annotations_page import AnnotationsPage
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
from ui.pages.ocr_page import OCRPage
from ui.pages.page_numbers_page import PageNumbersPage
from ui.pages.pages_page import PagesPage
from ui.pages.protect_page import ProtectPage
from ui.pages.redaction_page import RedactionPage
from ui.pages.signature_page import SignaturePage
from ui.pages.split_page import SplitPage
from ui.pages.watermark_page import WatermarkPage
from ui.theme import apply_dark_titlebar
from ui.widgets.page_container import PageContainer

APP_VERSION = "0.2.0"


def _build_sections():
    return [
        (
            build_create_icon,
            tr("Criar PDF"),
            tr("Crie um novo PDF em branco, com uma ou mais páginas."),
            CreatePage,
        ),
        (
            build_merge_icon,
            tr("Mesclar"),
            tr("Combine vários PDFs em um único arquivo, na ordem que você escolher."),
            MergePage,
        ),
        (
            build_split_icon,
            tr("Dividir"),
            tr("Separe um PDF em vários arquivos menores."),
            SplitPage,
        ),
        (
            build_pages_icon,
            tr("Páginas"),
            tr("Rotacione, reordene ou remova páginas de um PDF."),
            PagesPage,
        ),
        (
            build_compress_icon,
            tr("Comprimir"),
            tr("Reduza o tamanho de um arquivo PDF."),
            CompressPage,
        ),
        (
            build_convert_icon,
            tr("Converter"),
            tr("Converta entre PDF e imagens, documentos do Office (Word/Excel/PowerPoint) e XML."),
            ConvertPage,
        ),
        (
            build_watermark_icon,
            tr("Marca d'água"),
            tr("Adicione um texto de marca d'água sobre as páginas de um PDF."),
            WatermarkPage,
        ),
        (
            build_protect_icon,
            tr("Proteger"),
            tr("Proteja um PDF com senha, ou remova a senha de um PDF protegido."),
            ProtectPage,
        ),
        (
            build_metadata_icon,
            tr("Metadados"),
            tr("Edite título, autor, assunto e palavras-chave de um PDF."),
            MetadataPage,
        ),
        (
            build_page_numbers_icon,
            tr("Numeração"),
            tr("Adicione números de página no rodapé de um PDF."),
            PageNumbersPage,
        ),
        (
            build_extract_text_icon,
            tr("Extrair texto"),
            tr("Extraia todo o texto de um PDF para um arquivo .txt."),
            ExtractTextPage,
        ),
        (
            build_extract_images_icon,
            tr("Extrair imagens"),
            tr("Extraia as imagens embutidas nas páginas de um PDF."),
            ExtractImagesPage,
        ),
        (
            build_crop_icon,
            tr("Cortar/Redimensionar"),
            tr("Corte margens ou redimensione as páginas de um PDF."),
            CropPage,
        ),
        (
            build_bookmarks_icon,
            tr("Marcadores"),
            tr("Monte um sumário de navegação (marcadores) para um PDF."),
            BookmarksPage,
        ),
        (
            build_form_fields_icon,
            tr("Campos de formulário"),
            tr("Adicione campos de formulário interativos (texto ou caixa de seleção) a um PDF."),
            FormFieldsPage,
        ),
        (
            build_annotations_icon,
            tr("Anotações"),
            tr("Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF."),
            AnnotationsPage,
        ),
        (
            build_ocr_icon,
            tr("OCR"),
            tr("Reconheça o texto de PDFs escaneados e gere um PDF pesquisável."),
            OCRPage,
        ),
        (
            build_redaction_icon,
            tr("Redigir/Sanitizar"),
            tr("Apague definitivamente áreas de um PDF ou remova metadados, JavaScript e anexos."),
            RedactionPage,
        ),
        (
            build_signature_icon,
            tr("Assinatura digital"),
            tr("Assine um PDF com selo visível e assinatura criptográfica, ou verifique uma assinatura existente."),
            SignaturePage,
        ),
    ]


class MainWindow(QMainWindow):
    """Janela principal do OpenFolio PDF Suite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenFolio PDF Suite")
        self.setWindowIcon(build_app_icon())
        self.resize(1440, 820)

        # A sessão e os estados de anotações/redação precisam sobreviver à reconstrução
        # da UI ao trocar de idioma, por isso vivem no __init__ e não em _build_ui().
        self.session = DocumentSession()
        self.annotation_state = AnnotationState()
        self.redaction_state = RedactionState()

        i18n.language_changed.changed.connect(self._on_language_changed)

        self._build_ui()
        apply_dark_titlebar(self)

    def _build_ui(self):
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)
        self.sidebar.setIconSize(QSize(20, 20))

        self.stack = QStackedWidget()
        self._annotations_row = None
        self._redaction_row = None

        for row, (build_icon, name, subtitle, page_class) in enumerate(_build_sections()):
            item = QListWidgetItem(name)
            item.setIcon(build_icon())
            self.sidebar.addItem(item)

            if page_class is AnnotationsPage:
                self._annotations_row = row
                content = page_class(self.session, self.annotation_state)
            elif page_class is RedactionPage:
                self._redaction_row = row
                content = page_class(self.session, self.redaction_state)
            else:
                content = page_class(self.session)

            panel = PageContainer(name, subtitle, content)
            scroll_area = QScrollArea()
            scroll_area.setObjectName("toolPanelScroll")
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(panel)
            self.stack.addWidget(scroll_area)

        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        self.sidebar.setCurrentRow(0)

        self.viewer = PdfViewer(self.session, self.annotation_state, self.redaction_state)

        self.stack.setFixedWidth(480)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.viewer, 1)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self._build_menu_bar()
        self.statusBar().showMessage(f"OpenFolio PDF Suite {APP_VERSION}")

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu(tr("Arquivo"))
        open_action = file_menu.addAction(tr("Abrir PDF..."))
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_pdf)
        file_menu.addSeparator()
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
        us_button.setObjectName("flagButton")
        us_button.setIcon(build_us_flag_icon())
        us_button.setIconSize(icon_size)
        us_button.setToolTip("English")
        us_button.setFixedSize(38, 26)
        us_button.setCursor(Qt.CursorShape.PointingHandCursor)
        us_button.clicked.connect(lambda: i18n.set_language(i18n.EN_US))

        br_button = QPushButton()
        br_button.setObjectName("flagButton")
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

    def _on_sidebar_row_changed(self, row: int):
        self.stack.setCurrentIndex(row)
        # Fora da aba de Anotações, cliques no visualizador não devem ser interpretados
        # como desenho de marcação (mas a ferramenta escolhida continua selecionada para
        # quando o usuário voltar). Comparar cada estado com sua própria linha garante que
        # Anotações e Redação nunca fiquem ativas ao mesmo tempo.
        self.annotation_state.set_page_active(row == self._annotations_row)
        self.redaction_state.set_page_active(row == self._redaction_row)

    def _open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), "", "PDF (*.pdf)")
        if path:
            self.session.open(path)

    def _show_about(self):
        QMessageBox.about(
            self,
            tr("Sobre o OpenFolio PDF Suite"),
            tr(
                "<b>OpenFolio PDF Suite</b> — versão {version}<br><br>"
                "Suite completa e open source de manipulação de PDF, 100% local, sem paywall."
            ).format(version=APP_VERSION),
        )
