"""Uma aba de documento: o PDF aberto, o visualizador e as ferramentas.

    [barra do visualizador: abrir, páginas, zoom, modos de exibição, busca]
    [faixa da ferramenta aberta: ícone, nome .......................... Fechar]
    ┃ícones┃ miniaturas/marcadores/anexos ┃ documento ┃ painel da ferramenta ┃ícones das ferramentas┃

Cada aba tem a própria sessão (desfazer, salvar), os próprios estados de marcação e a própria
fila de operações: uma operação longa num documento não trava os outros. As ferramentas são
construídas na primeira vez em que são abertas na aba.
"""

import importlib
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import sidebar_icons
from ui.annotation_state import AnnotationState
from ui.area_pick_state import AreaPickState
from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.measure_state import MeasureState
from ui.redaction_state import RedactionState
from ui.tasks import TaskManager
from ui.tools import AREA_PICK_PAGES, QUICK_TOOLS, ROW_OF, SECTIONS
from ui.viewer.pdf_viewer import PdfViewer
from ui.viewer.viewer_icons import build_thumbnails_icon
from ui.widget_state import capture_state, restore_state
from ui.widgets.page_container import PageContainer
from ui.widgets.task_status import TaskStatus

PANEL_WIDTH = 480
PANEL_MIN_WIDTH = 340
VIEWER_MIN_WIDTH = 320

# Os botões da coluna da esquerda, na ordem das abas do painel lateral do visualizador.
_LEFT_RAIL = [
    (build_thumbnails_icon, "Miniaturas das páginas"),
    (sidebar_icons.build_bookmarks_icon, "Marcadores"),
    (sidebar_icons.build_attachments_icon, "Anexos"),
]


def _rail_button(icon, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("railButton")
    button.setIcon(icon)
    button.setIconSize(QSize(22, 22))
    button.setFixedSize(40, 40)
    button.setCheckable(True)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tr(tooltip))
    return button


class DocumentTab(QWidget):
    changed = Signal()  # nome, histórico ou operação mudaram: a janela atualiza os menus e a aba
    tool_changed = Signal()
    all_tools_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("documentTab")
        self.session = DocumentSession()
        self.annotation_state = AnnotationState()
        self.redaction_state = RedactionState()
        self.measure_state = MeasureState()
        self.area_pick_state = AreaPickState()
        self.tasks = TaskManager(self)  # o run_task das ferramentas acha o da aba subindo pelos pais
        self._pages: dict[int, QWidget] = {}  # linha de SECTIONS -> ferramenta já construída
        self._tool = -1

        self._build_ui()
        self.task_status = TaskStatus(self.tasks)  # vai para a barra de status da janela

        self.tasks.started.connect(self.session.note_operation)
        self.tasks.started.connect(self._on_task_started)
        self.tasks.finished.connect(self._on_task_finished)
        self.session.history_changed.connect(self.changed)
        self.session.path_changed.connect(self.changed)
        self.session.path_changed.connect(self._update_left_rail)

    # -- montagem ------------------------------------------------------------

    def _build_ui(self):
        self.viewer = PdfViewer(
            self.session,
            self.annotation_state,
            self.redaction_state,
            self.measure_state,
            area_pick_state=self.area_pick_state,
        )
        self.viewer.setMinimumWidth(VIEWER_MIN_WIDTH)
        self.viewer.verify_signatures_requested.connect(self._verify_signatures)
        self.viewer.thumbnails_button.hide()  # a coluna de ícones da esquerda faz o papel dele

        self.tool_header = QWidget()
        self.tool_header.setObjectName("toolHeader")
        header_layout = QHBoxLayout(self.tool_header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        self._tool_icon = QLabel()
        self._tool_title = QLabel()
        self._tool_title.setObjectName("toolHeaderTitle")
        self.close_tool_button = QPushButton(tr("Fechar"))
        self.close_tool_button.setObjectName("closeToolButton")
        self.close_tool_button.clicked.connect(self.close_tool)
        header_layout.addWidget(self._tool_icon)
        header_layout.addWidget(self._tool_title)
        header_layout.addStretch()
        header_layout.addWidget(self.close_tool_button)
        self.tool_header.hide()

        self.stack = QStackedWidget()
        self.stack.setObjectName("toolPanel")
        self.stack.setMinimumWidth(PANEL_MIN_WIDTH)
        for _section in SECTIONS:
            scroll_area = QScrollArea()
            scroll_area.setObjectName("toolPanelScroll")
            scroll_area.setWidgetResizable(True)
            self.stack.addWidget(scroll_area)
        self.stack.hide()

        side_panel = self.viewer.side_panel
        side_panel.use_external_rail()
        side_panel.tabs_changed.connect(self._update_left_rail)

        self.left_rail = QWidget()
        self.left_rail.setObjectName("leftRail")
        left_layout = QVBoxLayout(self.left_rail)
        left_layout.setContentsMargins(4, 8, 4, 8)
        left_layout.setSpacing(4)
        self._left_buttons = []
        for index, (icon, tooltip) in enumerate(_LEFT_RAIL):
            button = _rail_button(icon(), tooltip)
            button.clicked.connect(lambda _checked=False, i=index: self._on_left_rail(i))
            left_layout.addWidget(button)
            self._left_buttons.append(button)
        left_layout.addStretch()

        self.right_rail = QWidget()
        self.right_rail.setObjectName("rightRail")
        right_layout = QVBoxLayout(self.right_rail)
        right_layout.setContentsMargins(4, 8, 4, 8)
        right_layout.setSpacing(4)
        self._quick_buttons: dict[int, QToolButton] = {}
        for class_name in QUICK_TOOLS:
            row = ROW_OF[class_name]
            icon, title = SECTIONS[row][0], SECTIONS[row][1]
            button = _rail_button(getattr(sidebar_icons, icon)(), title)
            button.clicked.connect(lambda _checked=False, r=row: self._on_quick_tool(r))
            right_layout.addWidget(button)
            self._quick_buttons[row] = button
        right_layout.addStretch()
        self.all_tools_button = _rail_button(sidebar_icons.build_all_tools_icon(), "Todas as ferramentas")
        self.all_tools_button.setCheckable(False)
        self.all_tools_button.clicked.connect(self.all_tools_requested)
        right_layout.addWidget(self.all_tools_button)

        # Divisores arrastáveis: o usuário escolhe quanto espaço dá ao documento.
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("documentSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(side_panel)
        self.splitter.addWidget(self.viewer)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.left_rail)
        body_layout.addWidget(self.splitter, 1)
        body_layout.addWidget(self.right_rail)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer.toolbar)  # sai do visualizador para cobrir a largura da aba
        layout.addWidget(self.tool_header)
        layout.addWidget(body, 1)
        self._update_left_rail()

    # -- painel lateral ----------------------------------------------------------

    def _on_left_rail(self, index: int):
        side_panel = self.viewer.side_panel
        if side_panel.isVisibleTo(self) and side_panel.currentIndex() == index:
            self.viewer.show_side_panel(False)  # clicar no botão aberto recolhe o painel
        else:
            side_panel.setCurrentIndex(index)
            self.viewer.show_side_panel(True)
        self._update_left_rail()

    def _update_left_rail(self, *_args):
        side_panel = self.viewer.side_panel
        has_document = self.session.path() is not None
        for index, button in enumerate(self._left_buttons):
            button.setVisible(side_panel.isTabVisible(index))
            button.setEnabled(has_document)
            # isVisibleTo: o PDF pode abrir antes de a janela aparecer ("Abrir com")
            shown = side_panel.isVisibleTo(self)
            button.setChecked(has_document and shown and side_panel.currentIndex() == index)

    # -- ferramentas ---------------------------------------------------------------

    def current_tool(self) -> int:
        """A linha (em `ui.tools.SECTIONS`) da ferramenta aberta, ou -1."""
        return self._tool

    def _page_content(self, row: int) -> QWidget:
        _icon, _title, _subtitle, module_name, class_name = SECTIONS[row]
        page_class = getattr(importlib.import_module(module_name), class_name)
        if class_name == "AnnotationsPage":
            return page_class(self.session, self.annotation_state)
        if class_name == "RedactionPage":
            return page_class(self.session, self.redaction_state)
        if class_name == "MeasurePage":
            return page_class(self.session, self.measure_state)
        if class_name in AREA_PICK_PAGES:
            return page_class(self.session, area_pick_state=self.area_pick_state)
        return page_class(self.session)

    def page(self, row: int) -> QWidget:
        """A ferramenta da linha `row`, construída na primeira vez (sem abri-la)."""
        page = self._pages.get(row)
        if page is None:
            page = self._page_content(row)
            _icon, title, subtitle, _module, _class = SECTIONS[row]
            self.stack.widget(row).setWidget(PageContainer(tr(title), tr(subtitle), page, show_title=False))
            self._pages[row] = page
            if hasattr(page, "edits_changed"):
                page.edits_changed.connect(self.changed)
        return page

    def pages(self) -> dict[int, QWidget]:
        return self._pages

    def open_tool(self, row: int) -> QWidget:
        """Abre a ferramenta no painel da direita, com a faixa do nome dela no topo."""
        page = self.page(row)
        first_time = not self.stack.isVisible()
        self.stack.setCurrentIndex(row)
        self.stack.show()
        if first_time:
            sizes = self.splitter.sizes()
            if sizes[2] < PANEL_MIN_WIDTH:
                total = sum(sizes)
                panel = min(PANEL_WIDTH, max(PANEL_MIN_WIDTH, total // 3))
                self.splitter.setSizes([sizes[0], max(VIEWER_MIN_WIDTH, total - sizes[0] - panel), panel])
        self._tool = row
        self._update_tool_header()
        self._activate_marking(row)
        self.tool_changed.emit()
        return page

    def close_tool(self) -> None:
        """"Fechar" da faixa: o painel some e o documento ganha a largura."""
        self._tool = -1
        self.stack.hide()
        self._update_tool_header()
        self._activate_marking(-1)
        self.tool_changed.emit()

    def _on_quick_tool(self, row: int):
        if self._tool == row:
            self.close_tool()  # clicar na ferramenta aberta a fecha
        else:
            self.open_tool(row)

    def _activate_marking(self, row: int):
        # Fora de Anotações, cliques no visualizador não são desenho de marcação (a ferramenta
        # escolhida continua guardada para a volta); cada estado só vale na própria ferramenta,
        # então Anotações e Redação nunca ficam ativas ao mesmo tempo.
        class_name = SECTIONS[row][4] if row >= 0 else ""
        self.annotation_state.set_page_active(class_name == "AnnotationsPage")
        self.redaction_state.set_page_active(class_name == "RedactionPage")
        self.measure_state.set_page_active(class_name == "MeasurePage")
        self.area_pick_state.set_active_page(self._pages.get(row))

    def _update_tool_header(self):
        for row, button in self._quick_buttons.items():
            button.setChecked(row == self._tool)
        if self._tool < 0:
            self.tool_header.hide()
            return
        icon, title = SECTIONS[self._tool][0], SECTIONS[self._tool][1]
        self._tool_icon.setPixmap(getattr(sidebar_icons, icon)().pixmap(20, 20))
        self._tool_title.setText(tr(title))
        self.tool_header.show()

    def page_with_edits(self):
        """A ferramenta aberta, se ela tem mudanças próprias a desfazer antes das do documento
        (a grade de Organizar páginas)."""
        page = self._pages.get(self._tool)
        return page if hasattr(page, "undo_edit") else None

    def _verify_signatures(self):
        """O botão "Verificar" do aviso de documento assinado: abre a Assinatura no modo de
        verificação e verifica o documento aberto."""
        page = self.open_tool(ROW_OF["SignaturePage"])
        page.mode_combo.setCurrentIndex(1)
        page._apply_verify()

    # -- operações em andamento --------------------------------------------------------

    def _on_task_started(self, _title: str):
        # Uma operação por vez em cada documento: o painel da ferramenta fica travado até ela
        # terminar. O visualizador continua livre para navegar, dar zoom e buscar.
        self.stack.setEnabled(False)
        self.changed.emit()

    def _on_task_finished(self, _outcome: str):
        self.stack.setEnabled(True)
        self.changed.emit()

    # -- idioma, nome e fechamento --------------------------------------------------------

    def retranslate(self):
        """Traduz a aba sem perder o documento nem o que estava preenchido nas ferramentas (que
        são reconstruídas, ver `ui/widget_state.py`)."""
        for row, old_page in list(self._pages.items()):
            state = capture_state(old_page)
            del self._pages[row]
            old_container = self.stack.widget(row).takeWidget()
            restore_state(self.page(row), state)
            if old_container is not None:
                old_container.deleteLater()
        self.area_pick_state.set_active_page(self._pages.get(self._tool))
        self.viewer.retranslate()
        self.task_status.retranslate()
        self.close_tool_button.setText(tr("Fechar"))
        for button, (_icon, tooltip) in zip(self._left_buttons, _LEFT_RAIL):
            button.setToolTip(tr(tooltip))
        for row, button in self._quick_buttons.items():
            button.setToolTip(tr(SECTIONS[row][1]))
        self.all_tools_button.setToolTip(tr("Todas as ferramentas"))
        self._update_tool_header()

    def is_empty(self) -> bool:
        return self.session.path() is None

    def title(self) -> str:
        """O nome do arquivo, com "*" se houver alterações não salvas."""
        source = self.session.source_path()
        if not source:
            return tr("Sem documento")
        return f"{Path(source).name}{' *' if self.session.is_modified() else ''}"

    def shutdown(self) -> None:
        """Ao fechar a aba: solta o arquivo no pdfium e apaga as versões temporárias."""
        self.viewer.close_document()
        self.session.discard_temporary_files()
