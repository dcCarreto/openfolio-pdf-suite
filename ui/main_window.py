"""Janela principal da aplicação."""

import importlib
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QByteArray, QProcess, QSettings, QSize, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from core import updates
from core.version import APP_VERSION
from core.properties import ReadDocumentProperties
from ui import i18n, sidebar_icons
from ui.annotation_state import AnnotationState
from ui.about_dialog import AboutDialog
from ui.app_events import pdf_paths_from_mime
from ui.area_pick_state import AreaPickState
from ui.diagnostics import log_path
from ui.document_session import DocumentSession
from ui.flags import build_br_flag_icon, build_us_flag_icon
from ui.errors import show_error
from ui.i18n import tr
from ui.icon import build_app_icon
from ui.measure_state import MeasureState
from ui.preferences import Preferences, start_folder, use_preferences
from ui.printing import page_count_for_printing, pages_to_print, print_pages
from ui.properties_dialog import DocumentPropertiesDialog
from ui.redaction_state import RedactionState
from ui.shortcuts import CommandPalette, ShortcutsDialog
from ui.tasks import TaskManager, call, run_task
from ui import desktop_integration, theme
from ui.theme import apply_titlebar
from ui.update_dialog import UpdateDialog
from ui.viewer import pdf_viewer as viewer_layouts
from ui.viewer.pdf_viewer import PdfViewer
from ui.widget_state import capture_state, restore_state
from ui.widgets.page_container import PageContainer
from ui.widgets.task_status import TaskStatus


# Abas que marcam áreas arrastando no visualizador (ver ui/area_pick_state.py).
_AREA_PICK_PAGES = {"EditPage", "FormFieldsPage", "CropPage", "SignaturePage", "FillSignPage"}

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
    ("build_organize_icon", "Organizar páginas",
     "Reordene arrastando, gire, duplique, exclua, insira páginas em branco ou extraia páginas.",
     "ui.pages.organize_page", "OrganizePage"),
    ("build_compress_icon", "Comprimir", "Reduza o tamanho de um arquivo PDF.",
     "ui.pages.compress_page", "CompressPage"),
    ("build_convert_icon", "Converter",
     "Converta entre PDF e imagens, Word, Excel, PowerPoint, texto, HTML, Markdown e XML.",
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
     "Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF; edite, remova e "
     "troque comentários por XFDF.",
     "ui.pages.annotations_page", "AnnotationsPage"),
    ("build_measure_icon", "Medição",
     "Meça a distância entre dois pontos de um PDF, arrastando no visualizador central.",
     "ui.pages.measure_page", "MeasurePage"),
    ("build_ocr_icon", "OCR", "Reconheça o texto de PDFs escaneados e gere um PDF pesquisável.",
     "ui.pages.ocr_page", "OCRPage"),
    ("build_scan_cleanup_icon", "Limpar escaneados",
     "Remova páginas em branco, endireite páginas tortas e corte as margens brancas de um escaneado.",
     "ui.pages.scan_cleanup_page", "ScanCleanupPage"),
    ("build_redaction_icon", "Redigir/Sanitizar",
     "Apague definitivamente áreas de um PDF ou remova metadados, JavaScript e anexos.",
     "ui.pages.redaction_page", "RedactionPage"),
    ("build_fill_sign_icon", "Preencher e assinar",
     "Coloque texto, data, assinatura desenhada ou em imagem e iniciais na página, sem certificado.",
     "ui.pages.fill_sign_page", "FillSignPage"),
    ("build_signature_icon", "Assinatura digital",
     "Assine um PDF com selo visível e assinatura criptográfica, ou verifique uma assinatura existente.",
     "ui.pages.signature_page", "SignaturePage"),
    ("build_accessibility_icon", "Acessibilidade",
     "Verifique um subconjunto de PDF/UA e corrija idioma/título do documento.",
     "ui.pages.accessibility_page", "AccessibilityPage"),
    ("build_compare_icon", "Comparar",
     "Compare duas versões de um PDF: lado a lado com as diferenças destacadas, diff de texto por página ou diff visual.",
     "ui.pages.compare_page", "ComparePage"),
    ("build_batch_icon", "Processar em lote",
     "Aplique a mesma operação (comprimir, OCR, marca d'água, numerar, proteger, PDF/A) a todos os PDFs de uma pasta.",
     "ui.pages.batch_page", "BatchPage"),
]

_SIDEBAR_WIDTH = 210
_PANEL_WIDTH = 480
_PANEL_MIN_WIDTH = 340
_VIEWER_MIN_WIDTH = 320


def _installs_updates() -> bool:
    """O app instalado no Windows baixa e instala a atualização; no Linux, no macOS e rodando
    do código-fonte, a página da atualização abre no navegador."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _update_folder() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "update"


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
        self._preferences = Preferences(settings)
        use_preferences(self._preferences)
        saved_language = self._preferences.language()
        if saved_language in (i18n.PT_BR, i18n.EN_US) and saved_language != i18n.get_language():
            i18n.set_language(saved_language)  # antes de montar a interface, que usa tr()

        # Sobrevivem à troca de idioma: o documento aberto, as marcações pendentes e o
        # visualizador (com zoom, página e modo de exibição) não são reconstruídos.
        self.session = DocumentSession()
        self.annotation_state = AnnotationState()
        self.redaction_state = RedactionState()
        self.measure_state = MeasureState()
        self.area_pick_state = AreaPickState()
        self._tasks = TaskManager(self)  # o das abas desta janela (run_task o acha como filho)

        self._row_of = {class_name: row for row, (*_rest, class_name) in enumerate(_SECTIONS)}
        self._annotations_row = self._row_of["AnnotationsPage"]
        self._redaction_row = self._row_of["RedactionPage"]
        self._measure_row = self._row_of["MeasurePage"]
        self._pages: dict[int, QWidget] = {}  # linha -> aba já construída
        self._default_shortcuts: dict[str, list[QKeySequence]] = {}  # chave do comando -> de fábrica

        self._build_ui()
        if self._preferences.page_layout() in viewer_layouts.LAYOUTS:
            self.viewer.set_layout(self._preferences.page_layout())  # antes do menu, que o marca
        # Só a escolha do usuário fica guardada: uma ferramenta de desenho força a página única.
        for button in (self.viewer.single_page_button, self.viewer.continuous_button, self.viewer.double_page_button):
            button.clicked.connect(self._remember_page_layout)
        self._build_menu_bar()
        self._restore_layout()
        apply_titlebar(self)

        i18n.install_qt_translator(QApplication.instance())
        i18n.language_changed.changed.connect(self._on_language_changed)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        self.viewer.layout_changed.connect(lambda layout: self._layout_actions[layout].setChecked(True))
        self._tasks.started.connect(self._on_task_started)
        self._tasks.started.connect(self.session.note_operation)
        self._tasks.finished.connect(self._on_task_finished)
        self.session.set_discard_confirmation(self._confirm_discard_changes)
        self.setAcceptDrops(True)  # soltar um PDF na janela abre o documento
        self.session.history_changed.connect(self._update_document_actions)
        self.session.path_changed.connect(self._remember_opened_document)
        self._update_document_actions()

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
        self.viewer.verify_signatures_requested.connect(self._verify_signatures)

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
        self.statusBar().showMessage("OpenFolio PDF Suite")

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
        if class_name in _AREA_PICK_PAGES:
            return page_class(self.session, area_pick_state=self.area_pick_state)
        return page_class(self.session)

    def _ensure_page(self, row: int) -> QWidget:
        """Constrói a aba na primeira vez em que ela é aberta."""
        page = self._pages.get(row)
        if page is None:
            page = self._page_content(row)
            _icon, title, subtitle, _module, _class = _SECTIONS[row]
            self.stack.widget(row).setWidget(PageContainer(tr(title), tr(subtitle), page))
            self._pages[row] = page
            if hasattr(page, "edits_changed"):
                page.edits_changed.connect(self._update_document_actions)
        return page

    def page(self, row: int) -> QWidget:
        """A aba da linha `row` da barra lateral (construída se ainda não foi)."""
        return self._ensure_page(row)

    def _command(self, menu, key: str, label: str, *shortcuts: str) -> QAction:
        """Ação de menu com chave estável (`objectName`), alcançável pela paleta de comandos
        e com atalho configurável; `shortcuts` são os de fábrica."""
        action = menu.addAction(label)
        action.setObjectName(key)
        action.setShortcuts(list(shortcuts))
        self._commands.append((menu.title(), action))
        return action

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()
        # (título do menu, ação), na ordem dos menus. Guardado aqui porque percorrer os menus
        # com QAction.menu() no PySide6 apaga o submenu quando o objeto Python é coletado.
        self._commands: list[tuple[str, QAction]] = []
        command = self._command

        file_menu = menu_bar.addMenu(tr("Arquivo"))
        command(file_menu, "file.open", tr("Abrir PDF..."), "Ctrl+O").triggered.connect(self._open_pdf)
        self._save_action = command(file_menu, "file.save", tr("Salvar"), "Ctrl+S")
        self._save_action.triggered.connect(self.save_document)
        self._save_as_action = command(file_menu, "file.save_as", tr("Salvar como..."), "Ctrl+Shift+S")
        self._save_as_action.triggered.connect(self.save_document_as)
        self._print_action = command(file_menu, "file.print", tr("Imprimir..."), "Ctrl+P")
        self._print_action.triggered.connect(self.print_document)
        self._properties_action = command(file_menu, "file.properties", tr("Propriedades do documento..."), "Ctrl+D")
        self._properties_action.triggered.connect(self.show_document_properties)
        self._recent_menu = file_menu.addMenu(tr("Abrir recente"))
        self._recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self._recent_menu.setEnabled(bool(self._preferences.recent_files()))
        file_menu.addSeparator()
        command(file_menu, "file.quit", tr("Sair"), "Ctrl+Q").triggered.connect(self.close)

        edit_menu = menu_bar.addMenu(tr("Editar"))
        self._undo_action = command(edit_menu, "edit.undo", tr("Desfazer"), "Ctrl+Z")
        self._undo_action.triggered.connect(self.undo)
        self._redo_action = command(edit_menu, "edit.redo", tr("Refazer"), "Ctrl+Y", "Ctrl+Shift+Z")
        self._redo_action.triggered.connect(self.redo)
        edit_menu.addSeparator()
        command(edit_menu, "edit.shortcuts", tr("Atalhos de teclado...")).triggered.connect(self.edit_shortcuts)

        view_menu = menu_bar.addMenu(tr("Exibir"))
        self._palette_action = command(view_menu, "view.palette", tr("Paleta de comandos..."), "Ctrl+K")
        self._palette_action.triggered.connect(self.show_command_palette)
        self._presentation_action = command(view_menu, "view.presentation", tr("Apresentação"), "F5", "Ctrl+L")
        self._presentation_action.triggered.connect(self.viewer.start_presentation)
        layout_menu = view_menu.addMenu(tr("Páginas"))
        layout_group = QActionGroup(layout_menu)
        self._layout_actions = {}
        for key, label in (
            (viewer_layouts.SINGLE, "Página única"),
            (viewer_layouts.CONTINUOUS, "Rolagem contínua"),
            (viewer_layouts.DOUBLE, "Página dupla"),
            (viewer_layouts.BOOK, "Livro (capa sozinha)"),
        ):
            action = command(layout_menu, f"view.layout.{key}", tr(label))
            action.setCheckable(True)
            action.setChecked(key == self.viewer.page_layout())
            action.triggered.connect(lambda _checked=False, k=key: self.viewer.set_layout(k))
            action.triggered.connect(self._remember_page_layout)
            layout_group.addAction(action)
            self._layout_actions[key] = action
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu(tr("Tema"))
        theme_group = QActionGroup(theme_menu)
        self._theme_actions = {}
        for key, label in ((theme.DARK, "Escuro"), (theme.LIGHT, "Claro"), (theme.SYSTEM, "Seguir o sistema")):
            action = command(theme_menu, f"view.theme.{key}", tr(label))
            action.setCheckable(True)
            action.setChecked(key == self._preferences.theme())
            action.triggered.connect(lambda _checked=False, k=key: self.set_theme(k))
            theme_group.addAction(action)
            self._theme_actions[key] = action

        help_menu = menu_bar.addMenu(tr("Ajuda"))
        update_action = command(help_menu, "help.check_updates", tr("Verificar atualizações..."))
        update_action.triggered.connect(lambda: self.check_for_updates(manual=True))
        self._update_on_start_action = command(help_menu, "help.check_updates_on_start", tr("Verificar atualizações ao iniciar"))
        self._update_on_start_action.setCheckable(True)
        self._update_on_start_action.setChecked(self._preferences.check_updates_on_start())
        self._update_on_start_action.toggled.connect(self._preferences.set_check_updates_on_start)
        if desktop_integration.appimage_path():
            self._app_menu_action = command(help_menu, "help.app_menu", tr("Mostrar no menu de aplicativos"))
            self._app_menu_action.setCheckable(True)
            self._app_menu_action.setChecked(desktop_integration.is_integrated())
            self._app_menu_action.toggled.connect(self._set_in_app_menu)
        help_menu.addSeparator()
        command(help_menu, "help.about", tr("Sobre o OpenFolio PDF Suite")).triggered.connect(self._show_about)

        # Uma ação por ferramenta, fora dos menus (a barra lateral já as lista), para a paleta
        # e para quem quiser um atalho direto para a aba.
        for action in getattr(self, "_tool_actions", []):
            self.removeAction(action)
            action.deleteLater()
        self._tool_actions = []
        for row, (_icon, title, subtitle, _module, class_name) in enumerate(_SECTIONS):
            action = QAction(self.sidebar.item(row).icon(), tr(title), self)
            action.setObjectName(f"tool.{class_name}")
            action.setStatusTip(tr(subtitle))
            action.triggered.connect(lambda _checked=False, r=row: self.sidebar.setCurrentRow(r))
            self.addAction(action)
            self._tool_actions.append(action)
            self._commands.append((tr("Ferramentas"), action))
        self._apply_shortcuts()
        if hasattr(self, "session"):
            self._update_document_actions()

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

    # -- comandos e atalhos (A18) ------------------------------------------------------

    def commands(self) -> list[tuple[str, QAction]]:
        """(rótulo, ação) de tudo o que a paleta de comandos e a tela de atalhos alcançam: as
        ações dos menus com chave e as das ferramentas. O rótulo usa o texto atual da ação
        ("Desfazer Comprimir")."""
        return [(f"{title} › {action.text()}", action) for title, action in self._commands]

    def _apply_shortcuts(self):
        for _label, action in self.commands():
            key = action.objectName()
            defaults = self._default_shortcuts.setdefault(key, action.shortcuts())
            custom = self._preferences.shortcut(key)
            action.setShortcuts(defaults if custom is None else [QKeySequence(custom)])

    def show_command_palette(self):
        palette = CommandPalette([c for c in self.commands() if c[1] is not self._palette_action], self)
        if palette.exec() and palette.chosen is not None:
            palette.chosen.trigger()

    def edit_shortcuts(self):
        dialog = ShortcutsDialog(self.commands(), self._default_shortcuts, self)
        if dialog.exec():
            for key, keys in dialog.changes().items():
                self._preferences.set_shortcut(key, keys)
            self._apply_shortcuts()

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
        self._preferences.set_language(i18n.get_language())
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
        self.area_pick_state.set_active_page(self._pages.get(self.sidebar.currentRow()))

        self.viewer.retranslate()
        self.task_status.retranslate()
        self._build_menu_bar()
        apply_titlebar(self)

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
        self.area_pick_state.set_active_page(self._pages.get(row))
        self._update_document_actions()

    def _open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), start_folder(), "PDF (*.pdf)")
        if path:
            self.session.open(path)

    def _remember_opened_document(self):
        if self.session.last_change() == "document" and self.session.source_path():
            self._preferences.add_recent_file(self.session.source_path())
            self._recent_menu.setEnabled(True)

    def _fill_recent_menu(self):
        self._recent_menu.clear()
        recent = self._preferences.recent_files()
        for path in recent:
            action = self._recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self.session.open(p))
        if recent:
            self._recent_menu.addSeparator()
            clear_action = self._recent_menu.addAction(tr("Limpar lista"))
            clear_action.triggered.connect(self._clear_recent_files)
        else:
            empty = self._recent_menu.addAction(tr("Nenhum arquivo recente"))
            empty.setEnabled(False)

    def _clear_recent_files(self):
        self._preferences.clear_recent_files()
        self._recent_menu.setEnabled(False)

    # -- arrastar e soltar -----------------------------------------------------------

    def dragEnterEvent(self, event):
        if pdf_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = pdf_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.session.open(paths[0])

    # -- documento de trabalho ------------------------------------------------------

    def _page_with_edits(self):
        """A aba aberta, se ela tem mudanças próprias a desfazer antes das do documento
        (a grade de Organizar páginas)."""
        page = self._pages.get(self.sidebar.currentRow()) if hasattr(self, "sidebar") else None
        return page if hasattr(page, "undo_edit") else None

    def undo(self):
        editor = self._page_with_edits()
        if editor is not None and editor.can_undo_edit():
            editor.undo_edit()
        else:
            self.session.undo()

    def redo(self):
        editor = self._page_with_edits()
        if editor is not None and editor.can_redo_edit():
            editor.redo_edit()
        else:
            self.session.redo()

    def _update_document_actions(self):
        """Habilita salvar/desfazer/refazer conforme o histórico, com o nome da operação, e
        põe o arquivo (com "*" se alterado) no título da janela."""
        if not hasattr(self, "_undo_action"):
            return
        busy = self._tasks.is_busy()
        has_document = self.session.path() is not None
        editor = self._page_with_edits()
        grid_undo = editor is not None and editor.can_undo_edit()
        grid_redo = editor is not None and editor.can_redo_edit()
        undo_label = tr("edição na grade") if grid_undo else self.session.undo_label()
        redo_label = tr("edição na grade") if grid_redo else self.session.redo_label()
        self._undo_action.setText(tr("Desfazer {operation}").format(operation=undo_label) if undo_label else tr("Desfazer"))
        self._redo_action.setText(tr("Refazer {operation}").format(operation=redo_label) if redo_label else tr("Refazer"))
        self._undo_action.setEnabled((grid_undo or self.session.can_undo()) and not busy)
        self._redo_action.setEnabled((grid_redo or self.session.can_redo()) and not busy)
        self._save_action.setEnabled(has_document and self.session.is_modified() and not busy)
        self._save_as_action.setEnabled(has_document and not busy)
        self._print_action.setEnabled(has_document and not busy)
        self._properties_action.setEnabled(has_document and not busy)
        self._presentation_action.setEnabled(has_document)

        source = self.session.source_path()
        if source:
            marker = " *" if self.session.is_modified() else ""
            self.setWindowTitle(f"{Path(source).name}{marker} — OpenFolio PDF Suite")
        else:
            self.setWindowTitle("OpenFolio PDF Suite")

    def save_document(self) -> bool:
        """Grava o documento de trabalho no arquivo do usuário. Devolve False se falhar."""
        if self.session.path() is None:
            return True
        try:
            self.session.save()
        except OSError as exc:
            show_error(self, tr("Salvar"), tr("Não foi possível salvar o arquivo: {error}"), exc)
            return False
        self.statusBar().showMessage(tr("Documento salvo."), 5000)
        return True

    def save_document_as(self) -> bool:
        if self.session.path() is None:
            return True
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Salvar como"), start_folder(self.session.source_path()), "PDF (*.pdf)"
        )
        if not path:
            return False
        try:
            self.session.save_as(path)
            self._preferences.add_recent_file(path)
        except OSError as exc:
            show_error(self, tr("Salvar"), tr("Não foi possível salvar o arquivo: {error}"), exc)
            return False
        self.statusBar().showMessage(tr("Documento salvo."), 5000)
        return True

    def _confirm_discard_changes(self) -> bool:
        """Antes de trocar ou fechar um documento com alterações: salvar, descartar ou
        cancelar. Devolve True para seguir."""
        name = Path(self.session.source_path() or "").name
        answer = QMessageBox.question(
            self,
            tr("Alterações não salvas"),
            tr('"{name}" tem alterações que não foram salvas. Salvar antes?').format(name=name),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_document()
        return answer == QMessageBox.StandardButton.Discard

    def print_document(self):
        """Arquivo > Imprimir: diálogo do sistema e impressão em segundo plano."""
        path = self.session.path()
        if path is None:
            return
        try:
            page_count = page_count_for_printing(path)
        except Exception as exc:  # noqa: BLE001 — protegido, restrito ou corrompido
            show_error(self, tr("Imprimir"), "{error}", exc)
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(Path(self.session.source_path() or path).name)
        dialog = QPrintDialog(printer, self)
        dialog.setMinMax(1, page_count)
        dialog.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage, True)
        dialog.setOption(QPrintDialog.PrintDialogOption.PrintSelection, bool(self.session.selected_pages()))
        if dialog.exec():
            self.start_printing(printer, page_count)

    def show_document_properties(self) -> bool:
        """Arquivo > Propriedades do documento: lê em segundo plano e abre o diálogo."""
        path = self.session.path()
        if path is None:
            return False
        file_name = Path(self.session.source_path() or path).name
        modified = self.session.is_modified()

        def done(properties):
            self._properties_dialog = DocumentPropertiesDialog(properties, file_name, modified, self.session, self)
            self._properties_dialog.open()

        return run_task(
            self,
            tr("Propriedades do documento"),
            call(ReadDocumentProperties().run, path),
            on_success=done,
            error_message=tr("Não foi possível ler as propriedades: {error}"),
        )

    def start_printing(self, printer: QPrinter, page_count: int) -> bool:
        """Imprime as páginas escolhidas no diálogo (separado dele para os testes)."""
        path = self.session.path()
        assert path is not None  # Imprimir só fica habilitado com documento
        pages = pages_to_print(printer, page_count, self.session.current_page(), self.session.selected_pages())
        return run_task(
            self,
            tr("Imprimir"),
            lambda progress: print_pages(path, printer, pages, progress),
            on_success=lambda count: self.statusBar().showMessage(
                tr("{count} página(s) enviada(s) para a impressora.").format(count=count), 8000
            ),
            error_message=tr("Não foi possível imprimir: {error}"),
        )

    def _verify_signatures(self):
        """O botão "Verificar" do aviso de documento assinado: abre a aba Assinatura no modo
        de verificação e verifica o documento aberto."""
        row = self._row_of["SignaturePage"]
        self.sidebar.setCurrentRow(row)
        page = self._ensure_page(row)
        page.mode_combo.setCurrentIndex(1)
        page._apply_verify()

    def _remember_page_layout(self) -> None:
        """O modo de exibição escolhido (barra do visualizador ou Exibir > Páginas) vale para as
        próximas sessões."""
        self._preferences.set_page_layout(self.viewer.page_layout())

    def set_theme(self, key: str) -> None:
        """Exibir > Tema: aplica e guarda para as próximas sessões."""
        self._preferences.set_theme(key)
        self._theme_actions[key].setChecked(True)
        theme.apply_theme(cast(QApplication, QApplication.instance()), key)

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        if self._preferences.theme() == theme.SYSTEM:
            theme.apply_theme(cast(QApplication, QApplication.instance()), theme.SYSTEM)

    def check_for_updates(self, manual: bool = True) -> bool:
        """Ajuda > Verificar atualizações (e ao iniciar, se o usuário ligou). Consulta a lista
        pública de releases do GitHub; nada é baixado nem instalado sem o usuário ver o que
        mudou e aceitar. Sem `manual`, só avisa se houver atualização. Devolve False se já
        houver uma consulta em andamento."""
        if getattr(self, "_update_reply", None) is not None:
            return False
        if getattr(self, "_network", None) is None:
            self._network = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(updates.RELEASES_URL))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"OpenFolio-PDF-Suite/{APP_VERSION}")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(15_000)
        self._update_reply: QNetworkReply | None = self._network.get(request)
        self._update_reply.finished.connect(lambda: self._on_update_reply(manual))
        return True

    def _on_update_reply(self, manual: bool) -> None:
        reply, self._update_reply = self._update_reply, None
        assert reply is not None
        reply.deleteLater()
        releases = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                releases = json.loads(bytes(reply.readAll().data()))
            except ValueError:
                pass
        if not isinstance(releases, list):
            logging.getLogger("openfolio").warning("Verificação de atualização falhou: %s", reply.errorString())
            if manual:
                QMessageBox.warning(
                    self,
                    tr("Verificar atualizações"),
                    tr("Não foi possível verificar atualizações. Confira a conexão e tente de novo."),
                )
            return
        update = updates.newest_update(releases, APP_VERSION)
        if update is None:
            if manual:
                QMessageBox.information(self, tr("Verificar atualizações"), tr("O OpenFolio PDF Suite já está atualizado."))
            return
        can_install = _installs_updates() and update.installer_url is not None
        if UpdateDialog(update, can_install, self).exec() != QDialog.DialogCode.Accepted:
            return
        if can_install:
            self._download_update(update)
        else:
            QDesktopServices.openUrl(QUrl(update.page))

    def _download_update(self, update: updates.Update) -> None:
        """Baixa o instalador da atualização, com andamento e Cancelar, para conferir e
        instalar (`_on_update_downloaded`)."""
        folder = _update_folder()
        shutil.rmtree(folder, ignore_errors=True)  # só o instalador da última atualização fica
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / updates.INSTALLER_NAME
        output = open(target, "wb")
        assert update.installer_url is not None  # só chamado quando a release traz o instalador
        request = QNetworkRequest(QUrl(update.installer_url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"OpenFolio-PDF-Suite/{APP_VERSION}")
        reply = self._network.get(request)
        self._update_download: QNetworkReply | None = reply
        progress = QProgressDialog(tr("Baixando a atualização..."), tr("Cancelar"), 0, 100, self)
        progress.setWindowTitle(tr("Atualização"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        reply.readyRead.connect(lambda: output.write(reply.readAll().data()))
        reply.downloadProgress.connect(lambda done, total: progress.setValue(done * 100 // total) if total > 0 else None)
        progress.canceled.connect(reply.abort)
        reply.finished.connect(lambda: self._on_update_downloaded(reply, output, target, update, progress))

    def _on_update_downloaded(self, reply, output, target: Path, update: updates.Update, progress) -> None:
        output.write(reply.readAll().data())
        output.close()
        progress.close()
        reply.deleteLater()
        self._update_download = None
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            shutil.rmtree(target.parent, ignore_errors=True)
            return
        if reply.error() != QNetworkReply.NetworkError.NoError or not updates.installer_is_intact(target, update):
            logging.getLogger("openfolio").warning("Download da atualização falhou ou não confere: %s", reply.errorString())
            shutil.rmtree(target.parent, ignore_errors=True)
            QMessageBox.warning(
                self,
                tr("Atualização"),
                tr("Não foi possível baixar a atualização: o arquivo não chegou inteiro ou não confere "
                   "com o publicado. Nada foi instalado; tente de novo mais tarde."),
            )
            return
        QMessageBox.information(
            self,
            tr("Atualização"),
            tr("A atualização foi baixada e conferida. O app vai fechar para instalá-la e abre de novo "
               "quando terminar."),
        )
        # Todas as janelas: o instalador não atualiza com o app aberto.
        QApplication.closeAllWindows()
        if any(isinstance(w, MainWindow) and w.isVisible() for w in QApplication.topLevelWidgets()):
            return  # o usuário preferiu não fechar alguma (alterações não salvas)
        # Inno Setup sem perguntas: atualiza por cima, apaga os arquivos da instalação anterior
        # e abre o app de novo (packaging/windows/installer.iss).
        QProcess.startDetached(str(target), ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])

    def offer_app_menu(self) -> None:
        """No AppImage: na primeira vez, pergunta se o app deve aparecer no menu de aplicativos
        (e na escolha do programa para PDF); depois, só acompanha o arquivo se ele mudar de
        lugar."""
        appimage = desktop_integration.appimage_path()
        if appimage is None:
            return
        if self._preferences.app_menu_offered():
            try:
                desktop_integration.follow(appimage)
            except OSError:
                logger.warning("Não foi possível atualizar a entrada do menu de aplicativos", exc_info=True)
            return
        self._preferences.set_app_menu_offered(True)
        answer = QMessageBox.question(
            self,
            tr("Menu de aplicativos"),
            tr("Mostrar o OpenFolio no menu de aplicativos e na lista de programas para abrir PDF?\n\n"
               "Dá para mudar depois em Ajuda > Mostrar no menu de aplicativos."),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._app_menu_action.setChecked(True)

    def _set_in_app_menu(self, checked: bool) -> None:
        appimage = desktop_integration.appimage_path()
        try:
            if checked and appimage:
                desktop_integration.integrate(appimage)
            else:
                desktop_integration.remove()
        except OSError as exc:
            show_error(self, tr("Menu de aplicativos"), tr("Não foi possível mudar o menu de aplicativos: {error}"), exc)
            self._app_menu_action.blockSignals(True)
            self._app_menu_action.setChecked(desktop_integration.is_integrated())
            self._app_menu_action.blockSignals(False)

    def _show_about(self):
        AboutDialog(log_path(), self).exec()

    # -- operações em andamento ------------------------------------------------------

    def _on_task_started(self, _title: str):
        # Uma operação por vez: o painel de ferramentas fica travado até ela terminar. O
        # visualizador continua livre para navegar, dar zoom e buscar.
        self.stack.setEnabled(False)
        self._language_switcher.setEnabled(False)
        self.statusBar().clearMessage()
        self._update_document_actions()

    def _on_task_finished(self, outcome: str):
        self.stack.setEnabled(True)
        self._language_switcher.setEnabled(True)
        self._update_document_actions()
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
        if self.session.is_modified() and not self._confirm_discard_changes():
            event.ignore()
            return
        self._save_layout()
        self.viewer.close_document()
        self.session.discard_temporary_files()
        super().closeEvent(event)
