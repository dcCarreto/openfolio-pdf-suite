"""Uma aba de documento: o PDF aberto, o visualizador e as ferramentas.

    ┃ícones┃ miniaturas/marcadores/anexos ┃ [barra do visualizador] ┃ [nome da ferramenta  Fechar] ┃ícones das┃
    ┃      ┃                              ┃ documento               ┃ painel da ferramenta         ┃ferramen- ┃
    ┃      ┃                              ┃                         ┃                              ┃tas       ┃

Sem espaço para o documento, as miniaturas se recolhem sozinhas enquanto uma ferramenta está
aberta e voltam quando ela fecha; numa janela estreita, o painel da ferramenta vira uma gaveta
sobre o documento (`_apply_width_rules`). Cada ferramenta fica num `ToolPanel` (ui/tool_panel.py).

Cada aba tem a própria sessão (desfazer, salvar), os próprios estados de marcação e a própria
fila de operações: uma operação longa num documento não trava os outros. As ferramentas são
construídas na primeira vez em que são abertas na aba.
"""

import importlib
from pathlib import Path
from typing import cast

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import motion, sidebar_icons, theme
from ui.annotation_state import AnnotationState
from ui.area_pick_state import AreaPickState
from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.measure_state import MeasureState
from ui.redaction_state import RedactionState
from ui.tasks import TaskManager
from ui.tool_panel import ToolPanel
from ui.top_bar import BusySpinner, TabCloseButton
from ui.tools import AREA_PICK_PAGES, QUICK_TOOLS, ROW_OF, SECTIONS
from ui.viewer.markup_bar import TOP_INSET, MarkupBar
from ui.viewer.pdf_viewer import PdfViewer
from ui.viewer.viewer_icons import build_print_icon, build_thumbnails_icon
from ui.widget_state import capture_state, restore_state
from ui.widgets.task_status import TaskStatus

PANEL_WIDTH = 344
PANEL_MIN_WIDTH = 300
PANEL_MAX_WIDTH = 480
SIDE_WIDTH = 176
SIDE_MIN_WIDTH = 140
SIDE_MAX_WIDTH = 320
LEFT_RAIL_WIDTH = 48
RIGHT_RAIL_WIDTH = 52
VIEWER_MIN_WIDTH = 320
CENTER_MIN_WIDTH = 640  # menos que isso com uma ferramenta aberta: as miniaturas se recolhem
CROWDED_WIDTH = 1280  # abaixo disso, ferramenta aberta sempre recolhe as miniaturas
NARROW_WIDTH = 1180  # abaixo disso, parte da barra do visualizador vai para o "..." e o painel vira gaveta
DRAWER_WIDTH = 340
MARKUP_WIDTH = 960  # o centro que a barra de marcação inteira precisa: as miniaturas cedem antes

# Os botões da coluna da esquerda, na ordem das abas do painel lateral do visualizador.
_LEFT_RAIL = [
    (build_thumbnails_icon, "Miniaturas das páginas"),
    (sidebar_icons.build_bookmarks_icon, "Marcadores"),
    (sidebar_icons.build_attachments_icon, "Anexos"),
]


def _rail_button(icon, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setProperty("ofRole", "rail")
    button.setIcon(icon)
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(36, 36)
    button.setCheckable(True)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tr(tooltip))
    button.setAccessibleName(tr(tooltip))
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
        self._crowded = False  # ferramenta aberta sem espaço para as miniaturas
        self._side_auto_hidden = False  # as miniaturas se recolheram sozinhas (voltam depois)
        self._drawer = False  # janela estreita: o painel flutua sobre o documento
        self._drawer_hidden = False  # gaveta fechada com Esc ou clique na página (a ferramenta segue aberta)
        self._closing = False  # o painel está encolhendo até sumir
        self._tool_keys: dict[int, str] = {}  # o atalho de cada ferramenta, para as dicas do trilho
        self._busy_panel: ToolPanel | None = None
        self._center_widgets: list[QWidget] = []  # o que uma ferramenta põe no lugar do visualizador

        self._build_ui()
        self.task_status = TaskStatus(self.tasks)  # vai para a barra de status da janela
        # O "x" e o arco de operação em andamento: a janela os põe na aba deste documento.
        self.close_button = TabCloseButton()
        self.busy_spinner = BusySpinner()
        self.busy_spinner.hide()

        self.tasks.started.connect(self.session.note_operation)
        self.tasks.started.connect(self._on_task_started)
        self.tasks.progress_changed.connect(self._on_task_progress)
        self.tasks.finished.connect(self._on_task_finished)
        self.session.history_changed.connect(self.changed)
        self.session.path_changed.connect(self.changed)
        self.session.path_changed.connect(self._update_left_rail)
        self.session.path_changed.connect(self._update_markup_bar)

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
        self.viewer.remove_password_requested.connect(self._remove_password)
        self.viewer.thumbnails_button.hide()  # a coluna de ícones da esquerda faz o papel dele
        # Na ponta da barra: Imprimir e o selo de estado ("✓ Salvo" ou "● Alterações não
        # salvas" + Salvar). A janela liga os cliques.
        self.print_button = self.viewer._tool_button(build_print_icon(), "Imprimir... (Ctrl+P)")
        self.print_button.setEnabled(False)
        self.state_badge = QLabel()
        self.state_badge.setProperty("ofRole", "badge")
        self.state_badge.setFixedHeight(22)
        self.save_button = QPushButton()
        self.save_button.setProperty("ofVariant", "primary")
        self.save_button.setProperty("ofSize", "mini")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setEnabled(False)
        toolbar_layout = self.viewer.toolbar.layout()
        toolbar_layout.addWidget(self.print_button)
        toolbar_layout.addSpacing(4)
        toolbar_layout.addWidget(self.state_badge)
        toolbar_layout.addWidget(self.save_button)
        self._narrow = False

        # Um painel por ferramenta, construído na primeira vez em que ela é aberta.
        self.stack = QStackedWidget()
        self.stack.setObjectName("ToolStack")
        self.stack.setMinimumWidth(PANEL_MIN_WIDTH)
        self.stack.setMaximumWidth(PANEL_MAX_WIDTH)
        for _section in SECTIONS:
            self.stack.addWidget(QWidget())
        self.stack.hide()
        self.tool_panel = self.stack
        self.viewer.scroll_area.viewport().installEventFilter(self)  # clique na página fecha a gaveta

        # Com Anotações aberta, a barra de marcação flutua sobre a página.
        self.markup_bar = MarkupBar(self.annotation_state, self.viewer.scroll_area.viewport())
        self.markup_bar.save_requested.connect(lambda: self.page(ROW_OF["AnnotationsPage"]).save_to_document())
        self.viewer.scroll_area.verticalScrollBar().valueChanged.connect(lambda _value: self.markup_bar.note_scroll())

        side_panel = self.viewer.side_panel
        side_panel.use_external_rail()
        side_panel.tabs_changed.connect(self._update_left_rail)
        side_panel.setMinimumWidth(0)
        side_panel.setMaximumWidth(SIDE_MAX_WIDTH)
        # A lateral ganha um cabeçalho de 44 px (o que ela mostra e quantos são): ela e o
        # cabeçalho ficam num contêiner, que aparece e some junto com ela.
        self.side_title = QLabel()
        self.side_title.setObjectName("SideTitle")
        self.side_count = QLabel()
        self.side_count.setObjectName("SideCount")
        side_header = QWidget()
        side_header.setObjectName("SideHeader")
        side_header.setFixedHeight(44)
        header_layout = QHBoxLayout(side_header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.addWidget(self.side_title)
        header_layout.addStretch()
        header_layout.addWidget(self.side_count)
        self.side_container = QWidget()
        self.side_container.setObjectName("SidePanel")
        self.side_container.setMinimumWidth(SIDE_MIN_WIDTH)
        self.side_container.setMaximumWidth(SIDE_MAX_WIDTH)
        side_layout = QVBoxLayout(self.side_container)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(side_header)
        side_layout.addWidget(side_panel, 1)
        self.side_container.resize(SIDE_WIDTH, self.side_container.height())
        self.side_container.setVisible(not side_panel.isHidden())
        side_panel.visibility_changed.connect(self.side_container.setVisible)
        side_panel.currentChanged.connect(self._update_side_header)
        side_panel.tabs_changed.connect(self._update_side_header)
        self.viewer.thumbnail_list.model().rowsInserted.connect(self._update_side_header)
        self.viewer.thumbnail_list.model().modelReset.connect(self._update_side_header)

        self.left_rail = QWidget()
        self.left_rail.setObjectName("LeftRail")
        self.left_rail.setFixedWidth(LEFT_RAIL_WIDTH)
        left_layout = QVBoxLayout(self.left_rail)
        left_layout.setContentsMargins(6, 8, 6, 8)
        left_layout.setSpacing(4)
        self._left_buttons = []
        for index, (icon, tooltip) in enumerate(_LEFT_RAIL):
            button = _rail_button(icon(), tooltip)
            button.clicked.connect(lambda _checked=False, i=index: self._on_left_rail(i))
            left_layout.addWidget(button)
            self._left_buttons.append(button)
        left_layout.addStretch()

        self.right_rail = QWidget()
        self.right_rail.setObjectName("RightRail")
        self.right_rail.setFixedWidth(RIGHT_RAIL_WIDTH)
        right_layout = QVBoxLayout(self.right_rail)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(2)
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

        # A barra do visualizador fica só sobre o documento, não sobre os painéis.
        self.center = QWidget()
        self.center.setObjectName("CenterColumn")
        center_layout = QVBoxLayout(self.center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.viewer.toolbar)
        center_layout.addWidget(self.viewer, 1)

        # Divisores arrastáveis: o usuário escolhe quanto espaço dá ao documento. Com 1 px, o
        # Qt ainda deixa uns 5 px de área para pegar o divisor.
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("documentSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.side_container)
        self.splitter.addWidget(self.center)
        self.splitter.addWidget(self.tool_panel)
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
        layout.addWidget(body, 1)
        self._update_left_rail()

    # -- painel lateral ----------------------------------------------------------

    def _on_left_rail(self, index: int):
        self._side_auto_hidden = False  # a escolha agora é do usuário
        side_panel = self.viewer.side_panel
        if side_panel.isVisibleTo(self) and side_panel.currentIndex() == index:
            self.viewer.show_side_panel(False)  # clicar no botão aberto recolhe o painel
        else:
            side_panel.setCurrentIndex(index)
            self.viewer.show_side_panel(True)
        self._update_left_rail()

    def set_tool_shortcuts(self, keys: dict[int, str]) -> None:
        """As dicas do trilho da direita: o nome da ferramenta e o atalho dela, se houver."""
        self._tool_keys = keys
        for row, button in self._quick_buttons.items():
            name = tr(SECTIONS[row][1])
            button.setToolTip(f"{name} ({keys[row]})" if keys.get(row) else name)
            button.setAccessibleName(name)

    def _update_side_header(self, *_args):
        side_panel = self.viewer.side_panel
        index = side_panel.currentIndex()
        titles = [tr("Miniaturas"), tr("Marcadores"), tr("Anexos")]
        counts = [
            self.viewer.thumbnail_list.count(),
            side_panel.outline_tree.topLevelItemCount(),
            side_panel.attachments_list.count(),
        ]
        self.side_title.setText(titles[index] if 0 <= index < 3 else "")
        self.side_count.setText(str(counts[index]) if 0 <= index < 3 and counts[index] else "")

    def _update_left_rail(self, *_args):
        side_panel = self.viewer.side_panel
        has_document = self.session.path() is not None
        for button in self._quick_buttons.values():  # sem documento, os trilhos esperam um PDF
            button.setEnabled(has_document)
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
            icon, title, subtitle, _module, _class = SECTIONS[row]
            panel = ToolPanel(getattr(sidebar_icons, icon)(), tr(title), tr(subtitle), page, self.session, self.tasks)
            panel.close_requested.connect(self.close_tool)
            old = self.stack.widget(row)
            self.stack.removeWidget(old)
            self.stack.insertWidget(row, panel)
            old.deleteLater()
            if row == self._tool:
                self.stack.setCurrentIndex(row)
            self._pages[row] = page
            if hasattr(page, "edits_changed"):
                page.edits_changed.connect(self.changed)
        return page

    def panel(self, row: int) -> ToolPanel:
        """O painel (cabeçalho, seções e rodapé) da ferramenta da linha `row`."""
        self.page(row)
        return cast(ToolPanel, self.stack.widget(row))

    def current_panel(self) -> ToolPanel | None:
        return self.panel(self._tool) if self._tool >= 0 else None

    def run_current_tool(self) -> bool:
        """Ctrl+Enter: a ação principal da ferramenta aberta."""
        panel = self.current_panel()
        return panel is not None and panel.run()

    def pages(self) -> dict[int, QWidget]:
        return self._pages

    def open_tool(self, row: int) -> QWidget:
        """Abre a ferramenta no painel da direita, com a faixa do nome dela no topo."""
        page = self.page(row)
        first_time = self._tool < 0
        appearing = not self.stack.isVisibleTo(self) or self._closing
        self._closing = False
        self._tool = row
        self.stack.setCurrentIndex(row)
        self._drawer_hidden = False
        self.stack.show()
        if self._drawer:
            self.stack.raise_()
            if appearing:
                self._slide_drawer_in()
        else:
            # Formulário mais largo que os 344 px (uma lista, uma tabela): o painel alarga até 480.
            body = self.panel(row).body.minimumSizeHint().width()
            wanted = max(PANEL_WIDTH, min(PANEL_MAX_WIDTH, body))
            sizes = self.splitter.sizes()
            if appearing:
                self._resize_panel(0, max(wanted, sizes[2] if sizes[2] >= PANEL_MIN_WIDTH else PANEL_WIDTH))
            elif (first_time and sizes[2] < PANEL_MIN_WIDTH) or sizes[2] < wanted:
                total = sum(sizes)
                self.splitter.setSizes([sizes[0], max(VIEWER_MIN_WIDTH, total - sizes[0] - wanted), wanted])
        self._update_quick_buttons()
        self._activate_marking(row)
        self._update_center()
        self._apply_width_rules()
        self.tool_changed.emit()
        return page

    def close_tool(self) -> None:
        """"Fechar" da faixa: o painel some e o documento ganha a largura."""
        self._tool = -1
        if self._drawer or not self.stack.isVisibleTo(self):
            self.stack.hide()
        else:  # o painel encolhe até sumir
            self._closing = True
            self._resize_panel(self.splitter.sizes()[2], 0, self._finish_closing)
        self._update_quick_buttons()
        self._activate_marking(-1)
        self._update_center()
        self._apply_width_rules()
        self.tool_changed.emit()

    def _finish_closing(self):
        if self._closing:
            self._closing = False
            self.stack.hide()

    def _resize_panel(self, start: int, end: int, on_done=None) -> None:
        """O painel abre (de 0 à largura) ou fecha (até 0) no divisor, em 160 ms."""
        self.stack.setMinimumWidth(0)  # o divisor não deixaria passar de 300 no meio do caminho

        def step(width):
            sizes = self.splitter.sizes()
            total = sum(sizes)
            self.splitter.setSizes([sizes[0], max(0, total - sizes[0] - int(width)), int(width)])

        def done():
            self.stack.setMinimumWidth(PANEL_MIN_WIDTH)
            if on_done is not None:
                on_done()

        motion.animate_value(self.splitter, start, end, motion.MEDIUM, step, done)

    def _slide_drawer_in(self) -> None:
        """A gaveta entra deslizando 24 px da direita, com a opacidade de 0 a 1 (200 ms); ao
        terminar, o efeito de opacidade sai e a sombra volta."""
        self._place_drawer()
        end = self.stack.pos()
        motion.animate(self.stack, b"pos", end + QPoint(24, 0), end, motion.SLOW)
        motion.fade_in(self.stack, motion.SLOW, then=self._drawer_shadow)

    def _drawer_shadow(self) -> None:
        if self._drawer:
            self.stack.setGraphicsEffect(theme.floating_shadow(self.stack))

    # -- larguras ---------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_width_rules()

    def _apply_width_rules(self):
        """Janela estreita: a barra do visualizador guarda parte dos botões no "...". Com uma
        ferramenta aberta e o documento apertado (janela abaixo de 1280 px, ou sem espaço para
        a barra do visualizador inteira), as miniaturas se recolhem e voltam quando houver
        espaço de novo."""
        width = self.width()
        self.viewer.set_compact(width < NARROW_WIDTH)
        self._set_drawer(width < NARROW_WIDTH)
        if (width < NARROW_WIDTH) != self._narrow:
            self._narrow = width < NARROW_WIDTH
            self.update_state_badge()
        # Pelas larguras padrão dos painéis: o divisor já espreme os dois quando falta espaço.
        tool_open = self._tool >= 0
        center = width - LEFT_RAIL_WIDTH - RIGHT_RAIL_WIDTH - SIDE_WIDTH - PANEL_WIDTH
        # O centro precisa caber a barra do visualizador inteira (uns 700 px), não só 640, e a
        # de marcação, com Anotações aberta.
        needed = max(CENTER_MIN_WIDTH, self.viewer.toolbar.minimumSizeHint().width())
        if self.annotation_state.is_page_active():
            needed = max(needed, MARKUP_WIDTH)
        crowded = tool_open and (width < CROWDED_WIDTH or center < needed)
        self._update_markup_bar()
        if crowded == self._crowded:
            return
        self._crowded = crowded
        shown = self.viewer.side_panel.isVisibleTo(self)
        if crowded and shown:
            self._side_auto_hidden = True
            self.viewer.show_side_panel(False)
        elif not crowded and self._side_auto_hidden:
            self._side_auto_hidden = False
            self.viewer.show_side_panel(True)
        self._update_left_rail()

    # -- gaveta (janela estreita) -------------------------------------------------------

    def _set_drawer(self, on: bool) -> None:
        """Abaixo de 1180 px o painel sai do divisor e flutua sobre o documento, junto do
        trilho da direita; acima disso, volta para o lugar."""
        if on == self._drawer:
            if on:
                self._place_drawer()
            return
        self._drawer = on
        self.stack.setProperty("drawer", on)
        if on:
            self.stack.setParent(self)
            self.stack.setGraphicsEffect(theme.floating_shadow(self.stack))
            self._place_drawer()
        else:
            self.stack.setGraphicsEffect(None)  # type: ignore[arg-type]
            self.splitter.insertWidget(2, self.stack)
        self.stack.style().unpolish(self.stack)
        self.stack.style().polish(self.stack)
        self.stack.setVisible(self._tool >= 0 and not (on and self._drawer_hidden))
        if on:
            self.stack.raise_()

    def _place_drawer(self) -> None:
        top = self.viewer.toolbar.height()
        self.stack.setGeometry(self.width() - RIGHT_RAIL_WIDTH - DRAWER_WIDTH, top, DRAWER_WIDTH, self.height() - top)

    def is_drawer_open(self) -> bool:
        return self._drawer and self.stack.isVisibleTo(self)

    def hide_drawer(self) -> None:
        """Esc ou clique na página: a gaveta some, a ferramenta continua aberta (o botão dela
        no trilho a traz de volta)."""
        if self.is_drawer_open():
            self._drawer_hidden = True
            self.stack.hide()
            self._update_markup_bar()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress and self.is_drawer_open():
            self.hide_drawer()
        elif event.type() == QEvent.Type.Resize:
            self._update_markup_bar()  # o centro mudou (miniaturas recolhidas, divisor)
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and (self.is_drawer_open() or self._tool >= 0):
            if self.is_drawer_open():
                self.hide_drawer()
            else:
                self.close_tool()
            return
        super().keyPressEvent(event)

    def _on_quick_tool(self, row: int):
        if self._tool == row and self._drawer and self._drawer_hidden:
            self._drawer_hidden = False  # a gaveta estava fechada: volta
            self.stack.show()
            self.stack.raise_()
            self._slide_drawer_in()
            self._update_markup_bar()
        elif self._tool == row:
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
        self._update_markup_bar()

    def _update_markup_bar(self, *_args):
        """A barra de marcação: só com Anotações aberta e um documento; compacta numa janela
        estreita ou com o centro apertado, e centralizada à esquerda da gaveta aberta."""
        show = self.annotation_state.is_page_active() and self.session.path() is not None
        bar = self.markup_bar
        if show:
            inset = DRAWER_WIDTH if self.is_drawer_open() else 0
            available = self.viewer.scroll_area.viewport().width() - inset - 4
            # Inteira se couber; senão apertada; e só ícones abaixo de 1180 px ou sem espaço nem
            # para a apertada (a folga é pouca em 1440 px e a fonte muda um pouco de um sistema
            # para outro).
            full = bar.full_width()
            compact = self.width() < NARROW_WIDTH or bar.tight_width() > available
            bar.set_compact(compact)
            bar.set_tight(not compact and full > available)
            bar.set_right_inset(inset)
            bar.appear()
        else:
            bar.hide()
        self.viewer.set_top_inset(TOP_INSET if show else 0)

    def _update_center(self):
        """Uma ferramenta com `center_widget` (a grade de Organizar páginas) ocupa o lugar do
        visualizador e da barra dele enquanto está aberta."""
        page = self._pages.get(self._tool) if self._tool >= 0 else None
        widget = getattr(page, "center_widget", None)
        alive = {getattr(each, "center_widget", None) for each in self._pages.values()}
        for other in list(self._center_widgets):
            if other not in alive:  # a ferramenta foi refeita (troca de idioma)
                self._center_widgets.remove(other)
                other.deleteLater()
            elif other is not widget:
                other.hide()
        if widget is not None:
            if widget not in self._center_widgets:
                self.center.layout().addWidget(widget, 1)
                self._center_widgets.append(widget)
            widget.show()
        self.viewer.toolbar.setVisible(widget is None)
        self.viewer.setVisible(widget is None)

    def center_widget(self) -> QWidget | None:
        """O que está no lugar do visualizador agora, ou None."""
        return next((w for w in self._center_widgets if w.isVisibleTo(self)), None)

    def _update_quick_buttons(self):
        for row, button in self._quick_buttons.items():
            button.setChecked(row == self._tool)

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

    def _remove_password(self):
        """"Remover senha" do aviso de documento protegido: abre a ferramenta nesse modo."""
        page = self.open_tool(ROW_OF["ProtectPage"])
        page.mode_combo.setCurrentIndex(2)

    # -- operações em andamento --------------------------------------------------------

    def _on_task_started(self, title: str):
        # Uma operação por vez em cada documento: o painel da ferramenta mostra o andamento e
        # trava as opções até ela terminar. O visualizador continua livre para navegar, dar
        # zoom e buscar.
        self._busy_panel = self.current_panel()
        if self._busy_panel is not None:
            self._busy_panel.task_started(title)
        self.changed.emit()

    def _on_task_progress(self, done: int, total: int, message: str):
        if self._busy_panel is not None:
            self._busy_panel.task_progress(done, total, message)

    def _on_task_finished(self, outcome: str):
        panel, self._busy_panel = self._busy_panel, None
        if panel is not None:
            panel.task_finished(outcome)
        self.changed.emit()

    # -- idioma, nome e fechamento --------------------------------------------------------

    def retranslate(self):
        """Traduz a aba sem perder o documento nem o que estava preenchido nas ferramentas (que
        são reconstruídas, ver `ui/widget_state.py`)."""
        for row in list(self._pages):
            state = capture_state(self.panel(row).body)
            del self._pages[row]
            self.page(row)
            restore_state(self.panel(row).body, state)
        self.area_pick_state.set_active_page(self._pages.get(self._tool))
        self._update_center()
        self.viewer.retranslate()
        self.markup_bar.retranslate()
        self.task_status.retranslate()
        for button, (_icon, tooltip) in zip(self._left_buttons, _LEFT_RAIL):
            button.setToolTip(tr(tooltip))
        self.set_tool_shortcuts(self._tool_keys)
        self.all_tools_button.setToolTip(tr("Todas as ferramentas"))
        self._update_side_header()
        self.print_button.setToolTip(tr("Imprimir... (Ctrl+P)"))
        self.update_state_badge()
        self._update_quick_buttons()

    def update_state_badge(self) -> None:
        """O selo da barra do visualizador: "✓ Salvo" ou "● Alterações não salvas" com o botão
        Salvar (só "Não salvo" na janela estreita). Sem documento, nada."""
        has_document = self.session.path() is not None
        modified = has_document and self.session.is_modified()
        if modified:
            text = tr("Não salvo") if self._narrow else tr("Alterações não salvas")
            self.state_badge.setText(f"● {text}")
        else:
            self.state_badge.setText(f"✓ {tr('Salvo')}")
        self.state_badge.setProperty("state", "unsaved" if modified else "saved")
        self.state_badge.style().unpolish(self.state_badge)
        self.state_badge.style().polish(self.state_badge)
        self.state_badge.setVisible(has_document)
        self.save_button.setText(tr("Salvar"))
        self.save_button.setToolTip(tr("Salvar (Ctrl+S)"))
        self.save_button.setVisible(modified)

    def is_empty(self) -> bool:
        return self.session.path() is None

    def title(self) -> str:
        """O nome do arquivo. O estado (não salvo) fica no selo e no ponto da aba, não no nome."""
        source = self.session.source_path()
        return Path(source).name if source else tr("Sem documento")

    def shutdown(self) -> None:
        """Ao fechar a aba: solta o arquivo no pdfium e apaga as versões temporárias."""
        self.viewer.close_document()
        self.session.discard_temporary_files()
