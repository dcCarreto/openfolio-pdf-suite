"""Janela principal da aplicação."""

import importlib
import logging

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from ui import i18n, sidebar_icons
from ui.annotation_state import AnnotationState
from ui.area_pick_state import AreaPickState
from ui.document_session import DocumentSession
from ui.flags import build_br_flag_icon, build_us_flag_icon
from ui.i18n import tr
from ui.icon import build_app_icon
from ui.measure_state import MeasureState
from ui.redaction_state import RedactionState
from ui.tasks import task_manager
from ui.theme import apply_dark_titlebar
from ui.viewer.pdf_viewer import PdfViewer
from ui.widget_state import capture_state, restore_state
from ui.widgets.page_container import PageContainer
from ui.widgets.task_status import TaskStatus

APP_VERSION = "0.2.0"

logger = logging.getLogger(__name__)

# (ícone, título, subtítulo, módulo, classe). Os textos são traduzidos ao montar a tela; o
# módulo de cada aba só é importado quando ela é aberta pela primeira vez, o que tira da
# abertura do app o custo de bibliotecas pesadas como pyhanko (assinatura) e pytesseract (OCR).
_SECTIONS = [
    ("build_create_icon", "Criar PDF", "Crie um novo PDF em branco, com uma ou mais páginas.",
     "ui.pages.create_page", "CreatePage"),
    ("build_merge_icon", "Mesclar", "Combine vários PDFs em um único arquivo, na ordem que você escolher.",
     "ui.pages.merge_page", "MergePage"),
    ("build_split_icon", "Dividir", "Separe um PDF em vários arquivos menores.",
     "ui.pages.split_page", "SplitPage"),
    ("build_pages_icon", "Páginas", "Rotacione, reordene ou remova páginas de um PDF.",
     "ui.pages.pages_page", "PagesPage"),
    ("build_compress_icon", "Comprimir", "Reduza o tamanho de um arquivo PDF.",
     "ui.pages.compress_page", "CompressPage"),
    ("build_convert_icon", "Converter",
     "Converta entre PDF e imagens, documentos do Office (Word/Excel/PowerPoint) e XML.",
     "ui.pages.convert_page", "ConvertPage"),
    ("build_watermark_icon", "Marca d'água", "Adicione um texto de marca d'água sobre as páginas de um PDF.",
     "ui.pages.watermark_page", "WatermarkPage"),
    ("build_protect_icon", "Proteger", "Proteja um PDF com senha, ou remova a senha de um PDF protegido.",
     "ui.pages.protect_page", "ProtectPage"),
    ("build_metadata_icon", "Metadados", "Edite título, autor, assunto e palavras-chave de um PDF.",
     "ui.pages.metadata_page", "MetadataPage"),
    ("build_page_numbers_icon", "Numeração", "Adicione números de página no rodapé de um PDF, ou numeração Bates.",
     "ui.pages.page_numbers_page", "PageNumbersPage"),
    ("build_pdfa_icon", "PDF/A",
     "Converta um PDF para uma aproximação de PDF/A (arquivamento) ou valide um existente.",
     "ui.pages.pdfa_page", "PDFAPage"),
    ("build_extract_text_icon", "Extrair texto", "Extraia todo o texto de um PDF para um arquivo .txt.",
     "ui.pages.extract_text_page", "ExtractTextPage"),
    ("build_extract_images_icon", "Extrair imagens", "Extraia as imagens embutidas nas páginas de um PDF.",
     "ui.pages.extract_images_page", "ExtractImagesPage"),
    ("build_crop_icon", "Cortar/Redimensionar", "Corte margens ou redimensione as páginas de um PDF.",
     "ui.pages.crop_page", "CropPage"),
    ("build_edit_icon", "Editar",
     "Substitua imagens embutidas, cubra e reescreva texto, ou adicione/liste/remova links de um PDF.",
     "ui.pages.edit_page", "EditPage"),
    ("build_bookmarks_icon", "Marcadores", "Monte um sumário de navegação (marcadores) para um PDF.",
     "ui.pages.bookmarks_page", "BookmarksPage"),
    ("build_layers_icon", "Camadas",
     "Liste as camadas (Optional Content Groups) de um PDF e alterne a visibilidade padrão de cada uma.",
     "ui.pages.layers_page", "LayersPage"),
    ("build_attachments_icon", "Anexos", "Liste, adicione, remova ou extraia os anexos embutidos de um PDF.",
     "ui.pages.attachments_page", "AttachmentsPage"),
    ("build_form_fields_icon", "Campos de formulário",
     "Adicione campos de formulário e grupos de opções, liste os existentes, exporte/importe dados "
     "preenchidos ou achate o formulário.",
     "ui.pages.form_fields_page", "FormFieldsPage"),
    ("build_annotations_icon", "Anotações",
     "Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF.",
     "ui.pages.annotations_page", "AnnotationsPage"),
    ("build_measure_icon", "Medição",
     "Meça a distância entre dois pontos de um PDF, arrastando no visualizador central.",
     "ui.pages.measure_page", "MeasurePage"),
    ("build_ocr_icon", "OCR", "Reconheça o texto de PDFs escaneados e gere um PDF pesquisável.",
     "ui.pages.ocr_page", "OCRPage"),
    ("build_redaction_icon", "Redigir/Sanitizar",
     "Apague definitivamente áreas de um PDF ou remova metadados, JavaScript e anexos.",
     "ui.pages.redaction_page", "RedactionPage"),
    ("build_signature_icon", "Assinatura digital",
     "Assine um PDF com selo visível e assinatura criptográfica, ou verifique uma assinatura existente.",
     "ui.pages.signature_page", "SignaturePage"),
    ("build_accessibility_icon", "Acessibilidade",
     "Verifique um subconjunto de PDF/UA e corrija idioma/título do documento.",
     "ui.pages.accessibility_page", "AccessibilityPage"),
    ("build_compare_icon", "Comparar",
     "Compare duas versões de um PDF: diff de texto por página ou diff visual.",
     "ui.pages.compare_page", "ComparePage"),
]

_SIDEBAR_WIDTH = 210
_PANEL_WIDTH = 480
_PANEL_MIN_WIDTH = 340
_VIEWER_MIN_WIDTH = 320


class MainWindow(QMainWindow):
    """Janela principal do OpenFolio PDF Suite.

    `settings`, quando passado (o app real passa; os testes não), guarda o tamanho da
    janela e a largura dos painéis entre sessões.
    """

    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.setWindowTitle("OpenFolio PDF Suite")
        self.setWindowIcon(build_app_icon())
        self._settings = settings

        # Sobrevivem à troca de idioma: o documento aberto, as marcações pendentes e o
        # visualizador (com zoom, página e modo de exibição) não são reconstruídos.
        self.session = DocumentSession()
        self.annotation_state = AnnotationState()
        self.redaction_state = RedactionState()
        self.measure_state = MeasureState()
        self.area_pick_state = AreaPickState()
        self._tasks = task_manager()

        self._row_of = {class_name: row for row, (*_rest, class_name) in enumerate(_SECTIONS)}
        self._annotations_row = self._row_of["AnnotationsPage"]
        self._redaction_row = self._row_of["RedactionPage"]
        self._measure_row = self._row_of["MeasurePage"]
        self._edit_row = self._row_of["EditPage"]
        self._pages: dict[int, QWidget] = {}  # linha -> aba já construída

        self._build_ui()
        self._build_menu_bar()
        self._restore_layout()
        apply_dark_titlebar(self)

        i18n.install_qt_translator(QApplication.instance())
        i18n.language_changed.changed.connect(self._on_language_changed)
        self._tasks.started.connect(self._on_task_started)
        self._tasks.finished.connect(self._on_task_finished)

    # -- montagem ------------------------------------------------------------

    def _build_ui(self):
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setMinimumWidth(150)

        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(_PANEL_MIN_WIDTH)
        for build_icon, title, _subtitle, _module, _class in _SECTIONS:
            item = QListWidgetItem(tr(title))
            item.setIcon(getattr(sidebar_icons, build_icon)())
            self.sidebar.addItem(item)
            scroll_area = QScrollArea()
            scroll_area.setObjectName("toolPanelScroll")
            scroll_area.setWidgetResizable(True)
            self.stack.addWidget(scroll_area)

        self.viewer = PdfViewer(
            self.session,
            self.annotation_state,
            self.redaction_state,
            self.measure_state,
            area_pick_state=self.area_pick_state,
        )
        self.viewer.setMinimumWidth(_VIEWER_MIN_WIDTH)

        # Divisores arrastáveis no lugar das larguras fixas: a janela cabe em 1280x720
        # (notebook com escala de 150%) e o usuário escolhe quanto espaço dá ao documento.
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.viewer)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.setCentralWidget(self.splitter)

        self.task_status = TaskStatus(self._tasks)
        self.statusBar().addPermanentWidget(self.task_status)
        self.statusBar().showMessage(f"OpenFolio PDF Suite {APP_VERSION}")

        # Largura que mostra o nome mais longo inteiro mesmo com a barra de rolagem vertical
        # (que aparece em telas baixas, como 1280x720).
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._sidebar_width = max(
            _SIDEBAR_WIDTH,
            self.sidebar.sizeHintForColumn(0)
            + self.sidebar.verticalScrollBar().sizeHint().width()
            + 2 * self.sidebar.frameWidth(),
        )

        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        self.sidebar.setCurrentRow(0)

    def _page_content(self, row: int) -> QWidget:
        _icon, _title, _subtitle, module_name, class_name = _SECTIONS[row]
        page_class = getattr(importlib.import_module(module_name), class_name)
        if row == self._annotations_row:
            return page_class(self.session, self.annotation_state)
        if row == self._redaction_row:
            return page_class(self.session, self.redaction_state)
        if row == self._measure_row:
            return page_class(self.session, self.measure_state)
        if row == self._edit_row:
            return page_class(self.session, self.area_pick_state)
        return page_class(self.session)

    def _ensure_page(self, row: int) -> QWidget:
        """Constrói a aba na primeira vez em que ela é aberta."""
        page = self._pages.get(row)
        if page is None:
            page = self._page_content(row)
            _icon, title, subtitle, _module, _class = _SECTIONS[row]
            self.stack.widget(row).setWidget(PageContainer(tr(title), tr(subtitle), page))
            self._pages[row] = page
        return page

    def page(self, row: int) -> QWidget:
        """A aba da linha `row` da barra lateral (construída se ainda não foi)."""
        return self._ensure_page(row)

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
        self._language_switcher.setEnabled(not self._tasks.is_busy())

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

    # -- tamanho e posição -----------------------------------------------------

    def _restore_layout(self):
        geometry = self._settings.value("window/geometry") if self._settings else None
        splitter_state = self._settings.value("window/splitter") if self._settings else None
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            if isinstance(splitter_state, QByteArray):
                self.splitter.restoreState(splitter_state)
            return

        # Primeira abertura: ocupa até 90% da área útil da tela, sem passar do tamanho
        # pensado para o layout (1440x820).
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width, height = 1440, 820
        if available is not None:
            width = min(width, int(available.width() * 0.9))
            height = min(height, int(available.height() * 0.9))
        self.resize(width, height)
        panel = min(_PANEL_WIDTH, max(_PANEL_MIN_WIDTH, width // 3))
        sidebar = self._sidebar_width
        self.splitter.setSizes([sidebar, max(_VIEWER_MIN_WIDTH, width - panel - sidebar), panel])

    def _save_layout(self):
        if self._settings is None:
            return
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/splitter", self.splitter.saveState())

    # -- idioma ------------------------------------------------------------------

    def _on_language_changed(self):
        """Traduz a janela sem perder o que o usuário estava fazendo.

        A barra lateral, o menu e o visualizador só trocam os textos. As abas já abertas
        são reconstruídas (os textos delas são definidos na construção), recebendo de volta
        o que estava preenchido nelas (ver `ui/widget_state.py`).
        """
        i18n.install_qt_translator(QApplication.instance())
        for row, (_icon, title, _subtitle, _module, _class) in enumerate(_SECTIONS):
            self.sidebar.item(row).setText(tr(title))

        for row, old_page in list(self._pages.items()):
            state = capture_state(old_page)
            del self._pages[row]
            scroll_area = self.stack.widget(row)
            old_container = scroll_area.takeWidget()
            new_page = self._ensure_page(row)
            restore_state(new_page, state)
            if old_container is not None:
                old_container.deleteLater()

        self.viewer.retranslate()
        self.task_status.retranslate()
        self._build_menu_bar()
        apply_dark_titlebar(self)

    # -- navegação ---------------------------------------------------------------

    def _on_sidebar_row_changed(self, row: int):
        if row < 0:
            return
        self._ensure_page(row)
        self.stack.setCurrentIndex(row)
        # Fora da aba de Anotações, cliques no visualizador não devem ser interpretados
        # como desenho de marcação (mas a ferramenta escolhida continua selecionada para
        # quando o usuário voltar). Comparar cada estado com sua própria linha garante que
        # Anotações e Redação nunca fiquem ativas ao mesmo tempo.
        self.annotation_state.set_page_active(row == self._annotations_row)
        self.redaction_state.set_page_active(row == self._redaction_row)
        self.measure_state.set_page_active(row == self._measure_row)
        self.area_pick_state.set_page_active(row == self._edit_row)

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

    # -- operações em andamento ------------------------------------------------------

    def _on_task_started(self, _title: str):
        # Uma operação por vez: o painel de ferramentas fica travado até ela terminar. O
        # visualizador continua livre para navegar, dar zoom e buscar.
        self.stack.setEnabled(False)
        self._language_switcher.setEnabled(False)
        self.statusBar().clearMessage()

    def _on_task_finished(self, outcome: str):
        self.stack.setEnabled(True)
        self._language_switcher.setEnabled(True)
        if outcome == "cancelled":
            self.statusBar().showMessage(tr("Operação cancelada: nada foi gravado."), 8000)
        elif outcome == "ok":
            self.statusBar().showMessage(tr("Operação concluída."), 5000)

    def closeEvent(self, event):
        if self._tasks.is_busy():
            answer = QMessageBox.question(
                self,
                tr("Operação em andamento"),
                tr('"{task}" ainda está em andamento. Cancelar e sair?').format(task=self._tasks.title()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._tasks.cancel()
            # A operação para no próximo ponto seguro; como a gravação é atômica, nada
            # fica pela metade. Espera ela sair antes de fechar.
            if not self._tasks.wait(30_000):
                logger.warning("A operação não terminou a tempo ao fechar a janela")
        self._save_layout()
        super().closeEvent(event)
