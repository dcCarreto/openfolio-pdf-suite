"""Janela principal da aplicação.

Organizada em abas: Início, Ferramentas e uma aba por documento aberto (ver
`ui/document_tab.py`). Os menus, a barra de status e as ações de documento (salvar, desfazer,
imprimir...) valem para a aba de documento atual.
"""

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
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabBar,
    QTabWidget,
    QToolButton,
    QWidget,
)

from core import updates
from core.properties import ReadDocumentProperties
from core.version import APP_VERSION
from ui import desktop_integration, i18n, sidebar_icons, theme
from ui.about_dialog import AboutDialog
from ui.app_events import pdf_paths_from_mime
from ui.diagnostics import log_path
from ui.document_tab import PANEL_MIN_WIDTH, PANEL_WIDTH, VIEWER_MIN_WIDTH, DocumentTab
from ui.errors import show_error
from ui.flags import build_br_flag_icon, build_us_flag_icon
from ui.home_page import HomePage
from ui.i18n import tr
from ui.icon import build_app_icon
from ui.preferences import Preferences, start_folder, use_preferences
from ui.printing import page_count_for_printing, pages_to_print, print_pages
from ui.properties_dialog import DocumentPropertiesDialog
from ui.shortcuts import CommandPalette, ShortcutsDialog
from ui.tasks import call, run_task
from ui.theme import apply_titlebar
from ui.tools import ROW_OF, SECTIONS
from ui.tools_center import ToolsCenter
from ui.update_dialog import UpdateDialog
from ui.viewer import pdf_viewer as viewer_layouts
from ui.viewer.viewer_icons import build_close_icon

logger = logging.getLogger(__name__)

_SECTIONS = SECTIONS  # nome antigo, usado pelos testes que percorrem todas as ferramentas
_HOME, _TOOLS = 0, 1  # as abas fixas, antes das de documento


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

        self._row_of = ROW_OF
        self._annotations_row = ROW_OF["AnnotationsPage"]
        self._redaction_row = ROW_OF["RedactionPage"]
        self._measure_row = ROW_OF["MeasurePage"]
        self._active: DocumentTab | None = None  # a aba de documento atual (ou a última visitada)
        self._default_shortcuts: dict[str, list[QKeySequence]] = {}  # chave do comando -> de fábrica

        self._build_ui()
        self._build_menu_bar()
        self._restore_layout()
        apply_titlebar(self)

        i18n.install_qt_translator(QApplication.instance())
        i18n.language_changed.changed.connect(self._on_language_changed)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        self.setAcceptDrops(True)  # soltar um PDF na janela abre o documento
        self._update_document_actions()

    # -- montagem ------------------------------------------------------------

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("documentTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.home = HomePage(self._preferences)
        self.home.open_requested.connect(self._on_home_open)
        self.home.tool_requested.connect(self.open_tool)
        self.tools_center = ToolsCenter()
        self.tools_center.tool_requested.connect(self.open_tool)
        self.tabs.addTab(self.home, "")
        self.tabs.addTab(self.tools_center, "")
        for index in (_HOME, _TOOLS):  # as abas fixas não fecham
            self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        self._retranslate_fixed_tabs()
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("OpenFolio PDF Suite")

    def _retranslate_fixed_tabs(self):
        self.tabs.setTabText(_HOME, tr("Início"))
        self.tabs.setTabText(_TOOLS, tr("Ferramentas"))

    # -- abas de documento --------------------------------------------------------

    def documents(self) -> list[DocumentTab]:
        return [w for i in range(self.tabs.count()) if isinstance(w := self.tabs.widget(i), DocumentTab)]

    @property
    def document(self) -> DocumentTab | None:
        """A aba de documento atual, ou a última visitada (com Início ou Ferramentas à frente)."""
        if self._active is not None and self._active in self.documents():
            return self._active
        documents = self.documents()
        return documents[-1] if documents else None

    def current_document(self) -> DocumentTab:
        """A aba de documento atual; sem nenhuma, uma vazia (como uma janela sem PDF)."""
        return self.document or self.new_document()

    def new_document(self) -> DocumentTab:
        """Uma aba de documento vazia, já à frente."""
        doc = DocumentTab()
        doc.viewer.open_path = self.open_document  # "Abrir" da barra abre em outra aba
        doc.session.set_discard_confirmation(lambda d=doc: self._confirm_discard_changes(d))
        doc.changed.connect(lambda d=doc: self._on_document_changed(d))
        doc.tool_changed.connect(self._update_document_actions)
        doc.all_tools_requested.connect(lambda: self.tabs.setCurrentIndex(_TOOLS))
        doc.session.path_changed.connect(lambda d=doc: self._remember_opened_document(d))
        doc.viewer.layout_changed.connect(lambda layout, d=doc: self._on_layout_changed(d, layout))
        if self._preferences.page_layout() in viewer_layouts.LAYOUTS:
            doc.viewer.set_layout(self._preferences.page_layout())
        # Só a escolha do usuário fica guardada: uma ferramenta de desenho força a página única.
        for button in (doc.viewer.single_page_button, doc.viewer.continuous_button, doc.viewer.double_page_button):
            button.clicked.connect(lambda _checked=False, d=doc: self._remember_page_layout(d))
        doc.tasks.finished.connect(lambda outcome, d=doc: self._on_task_finished(d, outcome))
        doc.save_button.clicked.connect(self.save_document)
        doc.print_button.clicked.connect(self.print_document)
        doc.task_status.hide()
        self.statusBar().addPermanentWidget(doc.task_status)
        index = self.tabs.addTab(doc, build_app_icon(), doc.title())
        # O "x" nas cores do tema, no lugar do botão nativo (vermelho no Windows).
        close_button = QToolButton()
        close_button.setObjectName("tabCloseButton")
        close_button.setIcon(build_close_icon())
        close_button.setIconSize(QSize(14, 14))
        close_button.setFixedSize(20, 20)
        close_button.setAutoRaise(True)
        close_button.setToolTip(tr("Fechar documento"))
        close_button.clicked.connect(lambda _checked=False, d=doc: self.close_document(d))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_button)
        self._apply_splitter_state(doc)
        self.tabs.setCurrentWidget(doc)
        return doc

    def open_document(self, path: str) -> DocumentTab:
        """Abre o PDF numa aba: a atual, se estiver vazia; senão, uma nova. Um PDF já aberto
        só volta para a frente."""
        for doc in self.documents():
            if doc.session.source_path() and Path(doc.session.source_path()).resolve() == Path(path).resolve():
                self.tabs.setCurrentWidget(doc)
                return doc
        doc = self.document if self.document is not None and self.document.is_empty() else self.new_document()
        self.tabs.setCurrentWidget(doc)
        doc.session.open(path)
        return doc

    def open_tool(self, row: int) -> QWidget:
        """Abre a ferramenta na aba de documento atual (numa vazia, se não houver documento)."""
        doc = self.current_document()
        self.tabs.setCurrentWidget(doc)
        return doc.open_tool(row)

    def close_document(self, doc: DocumentTab) -> bool:
        """Fecha a aba (perguntando antes, se houver operação ou alterações). Devolve False se o
        usuário desistiu."""
        if not self._stop_task(doc) or (doc.session.is_modified() and not self._confirm_discard_changes(doc)):
            return False
        self._save_splitter_state(doc)
        index = self.tabs.indexOf(doc)
        if self._active is doc:
            self._active = None
        self.tabs.removeTab(index)
        self.statusBar().removeWidget(doc.task_status)
        doc.shutdown()
        doc.task_status.deleteLater()
        doc.deleteLater()
        if not self.documents():
            self.tabs.setCurrentIndex(_HOME)
        self._update_document_actions()
        return True

    def _on_tab_close_requested(self, index: int):
        widget = self.tabs.widget(index)
        if isinstance(widget, DocumentTab):
            self.close_document(widget)

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if isinstance(widget, DocumentTab):
            self._active = widget
        elif widget is self.home:
            self.home.refresh()
        for doc in self.documents():  # a barra de status mostra a operação do documento da frente
            doc.task_status.setVisible(doc is self.document and doc.tasks.is_busy())
        self._update_document_actions()

    def _on_document_changed(self, doc: DocumentTab):
        index = self.tabs.indexOf(doc)
        if index >= 0:
            self.tabs.setTabText(index, doc.title())
            self.tabs.setTabToolTip(index, doc.session.source_path() or "")
        if doc is self.document:
            doc.task_status.setVisible(doc.tasks.is_busy())
        self._update_document_actions()

    # Atalhos para a aba de documento atual: o resto do app (e os testes) fala com a janela.

    @property
    def session(self):
        return self.current_document().session

    @property
    def viewer(self):
        return self.current_document().viewer

    @property
    def annotation_state(self):
        return self.current_document().annotation_state

    @property
    def redaction_state(self):
        return self.current_document().redaction_state

    @property
    def measure_state(self):
        return self.current_document().measure_state

    @property
    def area_pick_state(self):
        return self.current_document().area_pick_state

    @property
    def stack(self):
        return self.current_document().stack

    @property
    def splitter(self):
        return self.current_document().splitter

    @property
    def task_status(self):
        return self.current_document().task_status

    @property
    def _tasks(self):
        return self.current_document().tasks

    @property
    def _pages(self):
        return self.current_document().pages()

    def page(self, row: int) -> QWidget:
        """A ferramenta da linha `row` na aba de documento atual (construída se ainda não foi)."""
        return self.current_document().page(row)

    def _ensure_page(self, row: int) -> QWidget:
        return self.page(row)

    # -- menus ---------------------------------------------------------------

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
        self._close_tab_action = command(file_menu, "file.close_tab", tr("Fechar documento"), "Ctrl+W")
        self._close_tab_action.triggered.connect(lambda: self.document is not None and self.close_document(self.document))
        command(file_menu, "file.quit", tr("Sair"), "Ctrl+Q").triggered.connect(self.close)

        edit_menu = menu_bar.addMenu(tr("Editar"))
        self._undo_action = command(edit_menu, "edit.undo", tr("Desfazer"), "Ctrl+Z")
        self._undo_action.triggered.connect(self.undo)
        self._redo_action = command(edit_menu, "edit.redo", tr("Refazer"), "Ctrl+Y", "Ctrl+Shift+Z")
        self._redo_action.triggered.connect(self.redo)
        edit_menu.addSeparator()
        command(edit_menu, "edit.shortcuts", tr("Atalhos de teclado...")).triggered.connect(self.edit_shortcuts)

        view_menu = menu_bar.addMenu(tr("Exibir"))
        command(view_menu, "view.home", tr("Início")).triggered.connect(lambda: self.tabs.setCurrentIndex(_HOME))
        command(view_menu, "view.tools", tr("Todas as ferramentas"), "Shift+F4").triggered.connect(
            lambda: self.tabs.setCurrentIndex(_TOOLS)
        )
        self._palette_action = command(view_menu, "view.palette", tr("Paleta de comandos..."), "Ctrl+K")
        self._palette_action.triggered.connect(self.show_command_palette)
        self._presentation_action = command(view_menu, "view.presentation", tr("Apresentação"), "F5", "Ctrl+L")
        self._presentation_action.triggered.connect(lambda: self.viewer.start_presentation())
        layout_menu = view_menu.addMenu(tr("Páginas"))
        layout_group = QActionGroup(layout_menu)
        self._layout_actions = {}
        current_layout = self.document.viewer.page_layout() if self.document else self._preferences.page_layout()
        for key, label in (
            (viewer_layouts.SINGLE, "Página única"),
            (viewer_layouts.CONTINUOUS, "Rolagem contínua"),
            (viewer_layouts.DOUBLE, "Página dupla"),
            (viewer_layouts.BOOK, "Livro (capa sozinha)"),
        ):
            action = command(layout_menu, f"view.layout.{key}", tr(label))
            action.setCheckable(True)
            action.setChecked(key == current_layout)
            action.triggered.connect(lambda _checked=False, k=key: self._choose_layout(k))
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

        # Uma ação por ferramenta, fora dos menus (a aba Ferramentas já as lista), para a paleta
        # e para quem quiser um atalho direto para ela.
        for action in getattr(self, "_tool_actions", []):
            self.removeAction(action)
            action.deleteLater()
        self._tool_actions = []
        for row, (icon, title, subtitle, _module, class_name) in enumerate(SECTIONS):
            action = QAction(getattr(sidebar_icons, icon)(), tr(title), self)
            action.setObjectName(f"tool.{class_name}")
            action.setStatusTip(tr(subtitle))
            action.triggered.connect(lambda _checked=False, r=row: self.open_tool(r))
            self.addAction(action)
            self._tool_actions.append(action)
            self._commands.append((tr("Ferramentas"), action))
        self._apply_shortcuts()
        self._update_document_actions()

        # Mantemos uma referência Python (self._language_switcher): sem ela, o PySide6
        # pode coletar o widget mesmo com o Qt "dono" dele internamente via setCornerWidget.
        self._language_switcher = self._build_language_switcher()
        menu_bar.setCornerWidget(self._language_switcher, Qt.Corner.TopRightCorner)
        # Ao reconstruir o menu (troca de idioma), o widget do canto não fica visível
        # sozinho sem um show() explícito.
        self._language_switcher.show()
        self._language_switcher.setEnabled(not self._any_busy())

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
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
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

    def _apply_splitter_state(self, doc: DocumentTab):
        """Cada documento novo abre com as larguras de painel que o usuário deixou por último."""
        state = self._settings.value("window/document_splitter") if self._settings else None
        if isinstance(state, QByteArray) and doc.splitter.restoreState(state):
            return
        width = max(self.width(), VIEWER_MIN_WIDTH + PANEL_MIN_WIDTH)
        panel = min(PANEL_WIDTH, max(PANEL_MIN_WIDTH, width // 3))
        side = doc.viewer.side_panel.width()
        doc.splitter.setSizes([side, max(VIEWER_MIN_WIDTH, width - panel - side), panel])

    def _save_splitter_state(self, doc: DocumentTab):
        if self._settings is not None:
            self._settings.setValue("window/document_splitter", doc.splitter.saveState())

    def _save_layout(self):
        if self._settings is None:
            return
        self._settings.setValue("window/geometry", self.saveGeometry())
        if self.document is not None:
            self._save_splitter_state(self.document)

    # -- idioma ------------------------------------------------------------------

    def _on_language_changed(self):
        """Traduz a janela sem perder o que o usuário estava fazendo: os documentos abertos e o
        que estava preenchido nas ferramentas continuam (ver `DocumentTab.retranslate`)."""
        i18n.install_qt_translator(QApplication.instance())
        self._preferences.set_language(i18n.get_language())
        self._retranslate_fixed_tabs()
        self.home.retranslate()
        self.tools_center.retranslate()
        for doc in self.documents():
            doc.retranslate()
            self._on_document_changed(doc)
        self._build_menu_bar()
        apply_titlebar(self)

    # -- abrir ---------------------------------------------------------------------

    def _open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), start_folder(), "PDF (*.pdf)")
        if path:
            self.open_document(path)

    def _on_home_open(self, path: str):
        if path:
            self.open_document(path)
        else:
            self._open_pdf()

    def _remember_opened_document(self, doc: DocumentTab):
        if doc.session.last_change() == "document" and doc.session.source_path():
            self._preferences.add_recent_file(doc.session.source_path())
            self._recent_menu.setEnabled(True)

    def _fill_recent_menu(self):
        self._recent_menu.clear()
        recent = self._preferences.recent_files()
        for path in recent:
            action = self._recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self.open_document(p))
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
        self.home.refresh()

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
            for path in paths:
                self.open_document(path)

    # -- documento de trabalho ------------------------------------------------------

    def _page_with_edits(self):
        return self.document.page_with_edits() if self.document is not None else None

    def undo(self):
        editor = self._page_with_edits()
        if editor is not None and editor.can_undo_edit():
            editor.undo_edit()
        elif self.document is not None:
            self.document.session.undo()

    def redo(self):
        editor = self._page_with_edits()
        if editor is not None and editor.can_redo_edit():
            editor.redo_edit()
        elif self.document is not None:
            self.document.session.redo()

    def _any_busy(self) -> bool:
        return any(doc.tasks.is_busy() for doc in self.documents())

    def _update_document_actions(self):
        """Habilita salvar/desfazer/refazer conforme o histórico do documento atual, com o nome
        da operação, e põe o arquivo (com "*" se alterado) no título da janela."""
        if not hasattr(self, "_undo_action"):
            return
        doc = self.document
        session = doc.session if doc is not None else None
        busy = doc is not None and doc.tasks.is_busy()
        has_document = session is not None and session.path() is not None
        editor = self._page_with_edits()
        grid_undo = editor is not None and editor.can_undo_edit()
        grid_redo = editor is not None and editor.can_redo_edit()
        undo_label = tr("edição na grade") if grid_undo else (session.undo_label() if session else "")
        redo_label = tr("edição na grade") if grid_redo else (session.redo_label() if session else "")
        self._undo_action.setText(tr("Desfazer {operation}").format(operation=undo_label) if undo_label else tr("Desfazer"))
        self._redo_action.setText(tr("Refazer {operation}").format(operation=redo_label) if redo_label else tr("Refazer"))
        self._undo_action.setEnabled((grid_undo or bool(session and session.can_undo())) and not busy)
        self._redo_action.setEnabled((grid_redo or bool(session and session.can_redo())) and not busy)
        self._save_action.setEnabled(has_document and bool(session and session.is_modified()) and not busy)
        self._save_as_action.setEnabled(has_document and not busy)
        self._print_action.setEnabled(has_document and not busy)
        self._properties_action.setEnabled(has_document and not busy)
        self._presentation_action.setEnabled(has_document)
        self._close_tab_action.setEnabled(doc is not None)
        for each in self.documents():  # os botões da barra de cada documento seguem o menu
            each_session = each.session
            each_busy = each.tasks.is_busy()
            each.save_button.setEnabled(each_session.path() is not None and each_session.is_modified() and not each_busy)
            each.print_button.setEnabled(each_session.path() is not None and not each_busy)
        if hasattr(self, "_language_switcher"):
            self._language_switcher.setEnabled(not self._any_busy())

        if doc is not None and session is not None and session.source_path():
            self.setWindowTitle(f"{doc.title()} — OpenFolio PDF Suite")
        else:
            self.setWindowTitle("OpenFolio PDF Suite")

    def save_document(self) -> bool:
        """Grava o documento de trabalho no arquivo do usuário. Devolve False se falhar."""
        doc = self.document
        if doc is None or doc.session.path() is None:
            return True
        try:
            doc.session.save()
        except OSError as exc:
            show_error(self, tr("Salvar"), tr("Não foi possível salvar o arquivo: {error}"), exc)
            return False
        self.statusBar().showMessage(tr("Documento salvo."), 5000)
        return True

    def save_document_as(self) -> bool:
        doc = self.document
        if doc is None or doc.session.path() is None:
            return True
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Salvar como"), start_folder(doc.session.source_path()), "PDF (*.pdf)"
        )
        if not path:
            return False
        try:
            doc.session.save_as(path)
            self._preferences.add_recent_file(path)
        except OSError as exc:
            show_error(self, tr("Salvar"), tr("Não foi possível salvar o arquivo: {error}"), exc)
            return False
        self.statusBar().showMessage(tr("Documento salvo."), 5000)
        return True

    def _confirm_discard_changes(self, doc: DocumentTab | None = None) -> bool:
        """Antes de trocar ou fechar um documento com alterações: salvar, descartar ou
        cancelar. Devolve True para seguir."""
        doc = doc or self.document
        if doc is None:
            return True
        self.tabs.setCurrentWidget(doc)  # o usuário vê de qual documento se trata
        name = Path(doc.session.source_path() or "").name
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
        path = self.session.path() if self.document is not None else None
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
        doc = self.document
        path = doc.session.path() if doc is not None else None
        if doc is None or path is None:
            return False
        file_name = Path(doc.session.source_path() or path).name
        modified = doc.session.is_modified()

        def done(properties):
            self._properties_dialog = DocumentPropertiesDialog(properties, file_name, modified, doc.session, self)
            self._properties_dialog.open()

        return run_task(
            doc,
            tr("Propriedades do documento"),
            call(ReadDocumentProperties().run, path),
            on_success=done,
            error_message=tr("Não foi possível ler as propriedades: {error}"),
        )

    def start_printing(self, printer: QPrinter, page_count: int) -> bool:
        """Imprime as páginas escolhidas no diálogo (separado dele para os testes)."""
        doc = self.current_document()
        path = doc.session.path()
        assert path is not None  # Imprimir só fica habilitado com documento
        pages = pages_to_print(printer, page_count, doc.session.current_page(), doc.session.selected_pages())
        return run_task(
            doc,
            tr("Imprimir"),
            lambda progress: print_pages(path, printer, pages, progress),
            on_success=lambda count: self.statusBar().showMessage(
                tr("{count} página(s) enviada(s) para a impressora.").format(count=count), 8000
            ),
            error_message=tr("Não foi possível imprimir: {error}"),
        )

    # -- modo de exibição ---------------------------------------------------------------

    def _choose_layout(self, layout: str) -> None:
        """Exibir > Páginas: vale para o documento atual e para as próximas sessões."""
        doc = self.current_document()
        doc.viewer.set_layout(layout)
        self._remember_page_layout(doc)

    def _remember_page_layout(self, doc: DocumentTab | None = None) -> None:
        """O modo de exibição escolhido (barra do visualizador ou Exibir > Páginas) vale para as
        próximas sessões."""
        self._preferences.set_page_layout((doc or self.current_document()).viewer.page_layout())

    def _on_layout_changed(self, doc: DocumentTab, layout: str) -> None:
        if doc is self.document and layout in self._layout_actions:
            self._layout_actions[layout].setChecked(True)

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
        self._preferences.set_last_update_check()  # a verificação ao iniciar espera um dia
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

    def _on_task_finished(self, doc: DocumentTab, outcome: str):
        if doc is not self.document:
            return  # o aviso é do documento que está na frente
        if outcome == "cancelled":
            self.statusBar().showMessage(tr("Operação cancelada: nada foi gravado."), 8000)
        elif outcome == "ok":
            self.statusBar().showMessage(tr("Operação concluída."), 5000)

    # -- fechar ----------------------------------------------------------------------

    def _stop_task(self, doc: DocumentTab) -> bool:
        """Com uma operação em andamento no documento, pergunta se cancela. Devolve False se o
        usuário preferiu esperar."""
        if not doc.tasks.is_busy():
            return True
        self.tabs.setCurrentWidget(doc)
        answer = QMessageBox.question(
            self,
            tr("Operação em andamento"),
            tr('"{task}" ainda está em andamento. Cancelar e sair?').format(task=doc.tasks.title()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        doc.tasks.cancel()
        # A operação para no próximo ponto seguro; como a gravação é atômica, nada fica pela
        # metade. Espera ela sair antes de fechar.
        if not doc.tasks.wait(30_000):
            logger.warning("A operação não terminou a tempo ao fechar o documento")
        return True

    def closeEvent(self, event):
        for doc in self.documents():
            if not self._stop_task(doc) or (doc.session.is_modified() and not self._confirm_discard_changes(doc)):
                event.ignore()
                return
        self._save_layout()
        for doc in self.documents():
            doc.shutdown()
        super().closeEvent(event)
