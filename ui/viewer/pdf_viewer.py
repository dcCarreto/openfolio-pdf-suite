"""Widget central: visualizador de PDF com miniaturas, zoom, página única/rolagem
contínua, busca de texto e preenchimento de formulários."""

import bisect
import dataclasses
import html
import time
from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QActionGroup, QColor, QCursor, QDesktopServices, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.annotations import STAMP_FONT_SIZE, AnnotationSpec, arrow_head, spec_rect, stamp_box
from core.base import known_password, remember_password
from core.document_info import document_notices, initial_view
from core.form_fields import FillFormFields, FormWidget, ListFormWidgets
from core.geometry import PageGeometry
from core.page_links import PageLink, PageNote, file_destination, linked_pdf_path, page_links, page_notes
from core.page_text import can_copy_text, char_at, line_range, word_range
from core.progress import PDFIUM_LOCK
from core.redaction import RedactionRect
from ui import theme
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.errors import show_error
from ui.i18n import tr, tr_message
from ui.area_pick_state import AreaPickState
from ui.measure_state import MeasureState, format_distance
from ui.redaction_state import RedactionState
from ui.preferences import preferences
from ui.tasks import run_task
from ui.viewer.page_canvas import PageCanvas
from ui.viewer.presentation import PresentationWindow
from ui.viewer.render import logical_size, render_page
from ui.viewer.search import DocumentSearch, SearchMatch
from ui.viewer.search_bar import SearchBar
from ui.viewer.side_panel import DocumentSidePanel
from ui.viewer.thumbnail_list import ThumbnailList
from ui.top_bar import bar_separator as _separator
from ui.viewer.viewer_icons import (
    build_book_icon,
    build_close_icon,
    build_continuous_page_icon,
    build_double_page_icon,
    build_file_icon,
    build_fit_width_icon,
    build_hand_icon,
    build_more_icon,
    build_next_page_icon,
    build_prev_page_icon,
    build_search_icon,
    build_single_page_icon,
    build_thumbnails_icon,
    build_zoom_in_icon,
    build_zoom_out_icon,
)

_MIN_SCALE = 0.3
_MAX_SCALE = 8.0  # páginas grandes demais perdem nitidez, não memória (`render_scale`)
_ZOOM_STEP = 0.15
_DEFAULT_SCALE = 1.2
_HIGHLIGHT_COLOR = QColor(255, 235, 59, 110)  # outras ocorrências da busca
_CURRENT_MATCH_COLOR = QColor(255, 152, 0, 150)  # a ocorrência atual
_TEXT_SELECTION_COLOR = QColor(33, 150, 243, 90)
_FORM_FIELD_COLOR = QColor(100, 149, 237, 45)  # campos preenchíveis, como nos leitores de PDF
_DRAWING_TOOLS = ("highlight", "underline", "strikeout", "note", "ink", "square", "circle", "arrow", "stamp")
_SHAPE_TOOLS = ("square", "circle", "arrow")
# A marcação pendente (só na ferramenta, ainda não gravada) ganha este contorno tracejado, igual
# nos dois temas: é uma cor das marcações sobre a página, não da interface.
PENDING_OUTLINE = "#b07800"
_RESIZE_HANDLE = 10  # pixels em volta do canto inferior direito que redimensionam
_LINK_CLICK_SLOP = 4  # pixels que o mouse pode andar entre apertar e soltar num link
_LINK_TARGET_MARGIN = 12  # o destino de um link fica um pouco abaixo do alto da tela
_HISTORY_LIMIT = 100  # posições guardadas para Voltar
_LINE_STEP = 40  # pixels de uma seta para cima ou para baixo
_SCREEN_OVERLAP = 40  # o que fica à vista de uma tela para a outra (barra de espaço)
_WHEEL_NOTCH = 120  # um dente da roda do mouse
# Rolagem contínua: páginas a mais de N alturas de tela da área visível têm a imagem
# descartada (voltam a ser renderizadas se o usuário rolar até elas). Antes nenhuma página
# era liberada e a memória crescia sem limite ao rolar documentos longos.
_KEEP_RENDERED_SCREENS = 3

# Layouts das páginas (A15). Página dupla e livro são a rolagem contínua com duas páginas
# por linha; no livro a capa fica sozinha, e as páginas pares à esquerda, como impressas.
SINGLE = "single"
CONTINUOUS = "continuous"
DOUBLE = "double"
BOOK = "book"
LAYOUTS = (SINGLE, CONTINUOUS, DOUBLE, BOOK)
_PAGE_GAP = 12
_NAMED_LINK_TIPS = {
    "NextPage": "Próxima página",
    "PrevPage": "Página anterior",
    "FirstPage": "Primeira página",
    "LastPage": "Última página",
    "GoBack": "Voltar",
    "GoForward": "Avançar",
}
# Busca incremental: tempo máximo por fatia antes de devolver o controle à janela.
_SEARCH_SLICE_SECONDS = 0.03


class PdfViewer(QWidget):
    """Mostra o PDF atualmente aberto na sessão compartilhada. A única edição feita aqui é
    preencher os campos de formulário (página única, sem ferramenta ativa): cada campo
    preenchido vira uma versão do documento, que Ctrl+Z desfaz e "Salvar" grava."""

    verify_signatures_requested = Signal()
    remove_password_requested = Signal()
    layout_changed = Signal(str)

    def __init__(
        self,
        session: DocumentSession,
        annotation_state: AnnotationState,
        redaction_state: RedactionState,
        measure_state: MeasureState | None = None,
        parent=None,
        area_pick_state: AreaPickState | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self.annotation_state = annotation_state
        self.redaction_state = redaction_state
        self.measure_state = measure_state or MeasureState()
        self.area_pick_state = area_pick_state or AreaPickState()
        # "Abrir PDF..." da barra: sozinho, troca o documento; numa aba de documento, abre outra aba.
        self.open_path = session.open
        self._document: pdfium.PdfDocument | None = None
        self._geometries: dict[int, PageGeometry] = {}  # geometria do arquivo, sem a rotação da tela
        self._view_rotation = 0  # "girar a visualização": só na tela, o arquivo não muda
        self._scale = _DEFAULT_SCALE
        self._continuous = False
        self._top_inset = 0  # espaço da barra de marcação acima da primeira página
        self._spread: str | None = None  # DOUBLE ou BOOK (com `_continuous`)
        self._show_thumbnails = True
        self._current_page = 0
        self._search = None
        self._matches: list[SearchMatch] = []
        self._current_match = -1
        self._page_labels: list[QLabel] = []
        self._page_tops: list[int] = []
        self._rendered_pages: set[int] = set()
        self._document_dependent_widgets: list[QWidget] = []
        self._drag_start_pdf: tuple[float, float] | None = None  # realce/sublinhado/riscado e carimbo
        self._drag_preview_base: QPixmap | None = None
        self._ink_points_pdf: list[tuple[float, float]] = []
        self._ink_preview_base: QPixmap | None = None
        self._shape_start_pdf: tuple[float, float] | None = None
        self._shape_preview_base: QPixmap | None = None
        # Arrastar o comentário escolhido (ferramenta Selecionar): "move" ou "resize", o
        # ponto inicial e o retângulo na tela, e a imagem da página sem a prévia.
        self._comment_drag: tuple[str, QPointF, QRectF] | None = None
        self._comment_drag_rect: QRectF | None = None
        self._comment_preview_base: QPixmap | None = None
        self._redaction_drag_start_pdf: tuple[float, float] | None = None
        self._area_drag_start_pdf: tuple[float, float] | None = None
        self._area_preview_base: QPixmap | None = None
        # Seleção de texto (sem ferramenta ativa): início do arrasto, página e trecho
        # selecionado (índices de caractere do pdfium) com os retângulos dele.
        self._selection_start_pdf: tuple[float, float] | None = None
        self._selection_start_page = 0
        self._selection_press: QPointF | None = None  # onde apertou: um clique não seleciona
        self._selection_anchor: int | None = None  # o caractere em que o arrasto começou
        # (primeira página, caractere nela, última página, caractere nela); -1: até o fim dela.
        self._text_selection: tuple[int, int, int, int] | None = None
        self._selection_rects: dict[int, list] = {}  # por página, lidos ao desenhar
        self._measure_drag_start_pdf: tuple[float, float] | None = None
        self._measure_preview_base: QPixmap | None = None
        self._form_widgets: list[FormWidget] = []
        self._field_editor: tuple[QLineEdit | QPlainTextEdit, FormWidget] | None = None
        self._links: dict[int, list[PageLink]] = {}  # por página, lidos na primeira vez
        self._notes: dict[int, list[PageNote]] = {}  # idem: os comentários com texto
        self._hover_target: PageLink | PageNote | FormWidget | None = None
        # O clique que pode seguir um link: página, o link sob o mouse e onde apertou.
        self._link_press: tuple[int, PageLink, QPointF] | None = None
        self._next_field: str | None = None  # o campo a abrir depois de gravar o atual (Tab)
        # Voltar e Avançar (Alt+setas): (página, fração da altura dela) antes de cada salto.
        self._back: list[tuple[int, float]] = []
        self._forward: list[tuple[int, float]] = []
        self._position_path: str | None = None  # o arquivo cuja página de leitura é lembrada
        self._page_names: dict[int, str] = {}  # rótulos do PDF ("iv"), lidos na primeira vez
        self._fit: str | None = None  # "width" ou "page": o zoom acompanha o tamanho da área
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(60)
        self._fit_timer.timeout.connect(self._refit)
        self._wheel_rest = 0  # o que a roda já andou na borda da página, para virá-la
        self._pan_from: QPointF | None = None  # arrastando a página com o botão do meio
        self._hand_mode = False  # ferramenta de mão: o botão esquerdo arrasta em vez de selecionar
        self._pan_travel = 0.0  # o quanto o mouse andou no arrasto atual
        self._single_scroll: int | None = None  # rolagem a aplicar quando o layout assentar
        self._zoom_anchor: tuple[float, float, QPointF] | None = None
        # O que precisa do layout assentado. Um timer filho, nunca QTimer.singleShot: fechada a
        # aba, um disparo pendente cairia num visualizador já destruído e derrubaria o app.
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(0)
        self._layout_timer.timeout.connect(self._after_layout)
        self._translatable_tooltips: list[tuple[QWidget, str]] = []
        self._dismissed_notices: set[str] = set()  # avisos fechados com o "x" (até outro documento)
        # Rolagem contínua: (página, fração da altura dela) a mostrar no topo assim que o
        # layout novo existir (depois de zoom ou troca de modo).
        self._pending_scroll: tuple[int, float] | None = None
        self._search_pages = None  # gerador da busca em andamento
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(0)
        self._search_timer.timeout.connect(self._continue_search)

        self._build_ui()
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._toggle_search)
        # Navegação pelo teclado com o foco no visualizador (os campos das abas continuam
        # recebendo as teclas normalmente).
        for keys, handler in (
            (("PgDown", "Right"), self._go_next),
            (("PgUp", "Left"), self._go_prev),
            (("Home",), self._go_first),
            (("End",), self._go_last),
            (("Ctrl+G",), self._ask_go_to_page),
            (("Ctrl+=", "Ctrl++"), self._zoom_in),
            (("Ctrl+-",), self._zoom_out),
            (("Ctrl+0",), self._fit_page),
            (("Ctrl+1",), lambda: self._set_zoom(100)),
            (("Ctrl+2",), self._fit_width),
            (("Ctrl+C",), self.copy_selected_text),
            (("F3",), lambda: self._step_search(1)),
            (("Shift+F3",), lambda: self._step_search(-1)),
            (("Alt+Left",), self.go_back),
            (("Alt+Right",), self.go_forward),
            (("Ctrl+Shift+H",), lambda: self.set_hand_mode(not self._hand_mode)),
        ):
            for key in keys:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(handler)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        # Só com o foco na página: as miniaturas e o sumário usam estas teclas para si.
        for key, handler in (
            ("Space", lambda: self._scroll_view(1, self._screen_step())),
            ("Shift+Space", lambda: self._scroll_view(-1, self._screen_step())),
            ("Down", lambda: self._scroll_view(1, _LINE_STEP)),
            ("Up", lambda: self._scroll_view(-1, _LINE_STEP)),
            ("Ctrl+A", self.select_all_text),
        ):
            shortcut = QShortcut(QKeySequence(key), self.scroll_area)
            shortcut.activated.connect(handler)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.scroll_area.viewport().installEventFilter(self)
        self.scroll_area.installEventFilter(self)

        session.path_changed.connect(self._reload)
        annotation_state.tool_changed.connect(self._on_markup_state_changed)
        annotation_state.pending_changed.connect(self._refresh_current_render)
        annotation_state.selection_changed.connect(self._on_comment_selection_changed)
        annotation_state.page_requested.connect(self._go_to_page)
        redaction_state.active_changed.connect(self._on_markup_state_changed)
        redaction_state.pending_changed.connect(self._refresh_current_render)
        redaction_state.selection_changed.connect(self._on_redaction_selection_changed)
        self.measure_state.active_changed.connect(self._on_markup_state_changed)
        self.measure_state.result_changed.connect(self._refresh_current_render)
        self.measure_state.unit_changed.connect(self._refresh_current_render)
        self.area_pick_state.active_changed.connect(self._on_markup_state_changed)
        self.area_pick_state.areas_changed.connect(self._on_picked_areas_changed)
        if session.path():
            self._reload()
        self._on_markup_state_changed()

    # -- construção da UI -------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # A aba de documento (ui/document_tab.py) leva a barra para o topo dela, acima dos painéis.
        self.toolbar = self._build_toolbar()
        layout.addWidget(self.toolbar)

        self.search_bar = SearchBar()
        self.search_bar.hide()
        self.search_bar.search_requested.connect(self._search_document)
        self.search_bar.next_requested.connect(lambda: self._step_match(1))
        self.search_bar.prev_requested.connect(lambda: self._step_match(-1))
        self.search_bar.closed.connect(self._close_search)
        layout.addWidget(self.search_bar)

        # Avisos sobre o documento aberto, uma faixa de 36 px por aviso, na cor do tipo:
        # protegido (com "Remover senha"), assinado (com "Ver"), formulário e camadas.
        self.notice_bar = QWidget()
        self._notice_layout = QVBoxLayout(self.notice_bar)
        self._notice_layout.setContentsMargins(0, 0, 0, 0)
        self._notice_layout.setSpacing(0)
        self.notice_bar.hide()
        self.verify_button: QPushButton | None = None
        layout.addWidget(self.notice_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.thumbnail_list = ThumbnailList()
        self.thumbnail_list.page_selected.connect(self._on_thumbnail_selected)
        self.thumbnail_list.pages_selected.connect(self.session.set_selected_pages)
        self.side_panel = DocumentSidePanel(self.thumbnail_list)
        self.side_panel.destination_requested.connect(self._jump_to_destination)
        self.side_panel.url_requested.connect(self._open_url)
        self.side_panel.file_requested.connect(lambda path: self.open_path(path))
        self.side_panel.hide()
        body_layout.addWidget(self.side_panel)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_empty_state())

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ViewerCanvas")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_pages)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._apply_pending_scroll)
        self.content_stack.addWidget(self.scroll_area)

        body_layout.addWidget(self.content_stack, 1)
        layout.addWidget(body, 1)

        self._set_document_controls_enabled(False)

    def _build_empty_state(self) -> QWidget:
        """Sem documento: a zona de soltar, com "Abrir arquivo..." e os recentes."""
        widget = QWidget()
        widget.setObjectName("ViewerEmpty")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        zone = QFrame()
        zone.setObjectName("DropZone")
        zone.setFixedWidth(440)
        icon = QLabel()
        icon.setPixmap(build_file_icon().pixmap(QSize(32, 32), QIcon.Mode.Selected))
        self._empty_label = QLabel()
        self._empty_label.setObjectName("EmptyTitle")
        self._empty_hint = QLabel()
        self._empty_hint.setProperty("ofRole", "secondary")
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_open_button = QPushButton()
        self._empty_open_button.setProperty("ofVariant", "primary")
        self._empty_open_button.clicked.connect(self._browse_open)
        self._empty_recent_button = QPushButton()
        recent_menu = QMenu(self._empty_recent_button)
        recent_menu.aboutToShow.connect(lambda: self._fill_recent_menu(recent_menu))
        self._empty_recent_button.setMenu(recent_menu)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        buttons.addWidget(self._empty_open_button)
        buttons.addWidget(self._empty_recent_button)
        buttons.addStretch()
        zone_layout = QVBoxLayout(zone)
        zone_layout.setContentsMargins(24, 28, 24, 28)
        zone_layout.setSpacing(10)
        zone_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        zone_layout.addWidget(self._empty_label, 0, Qt.AlignmentFlag.AlignHCenter)
        zone_layout.addWidget(self._empty_hint)
        zone_layout.addSpacing(6)
        zone_layout.addLayout(buttons)
        layout.addWidget(zone, 0, Qt.AlignmentFlag.AlignHCenter)
        self._retranslate_empty_state()
        return widget

    def retranslate(self):
        """Troca os textos para o idioma atual sem recarregar o documento nem perder zoom,
        página e modo de exibição."""
        for widget, text in self._translatable_tooltips:
            widget.setToolTip(tr(text))
            widget.setAccessibleName(tr(text))
        self._retranslate_toolbar_menus()
        self._retranslate_empty_state()
        self.search_bar.retranslate()
        self.thumbnail_list.retranslate()
        self.side_panel.retranslate()
        if getattr(self, "_notices", None) is not None:
            self._show_notices()
        self._update_page_indicator()

    def _build_toolbar(self) -> QWidget:
        """A barra sobre o documento (44 px), em grupos separados por traços:

            [< página de N >] | [- 120% +] | [ajuste ▾] | [modo ▾] | [buscar] ... (imprimir e o selo de estado)

        Abrir fica no "+" das abas e em Arquivo; a aba de documento põe Imprimir e o selo de
        estado (com "Salvar") na ponta. Estreita (`set_compact`), ajuste e modo vão para o "...".
        """
        toolbar = QWidget()
        toolbar.setObjectName("ViewerBar")
        toolbar.setFixedHeight(44)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        prev_button = self._tool_button(build_prev_page_icon(), "Página anterior")
        prev_button.clicked.connect(self._go_prev)
        next_button = self._tool_button(build_next_page_icon(), "Próxima página")
        next_button.clicked.connect(self._go_next)
        # O número da página atual, editável: Enter vai direto para a página digitada.
        self.page_field = QLineEdit()
        self.page_field.setObjectName("PageField")
        self.page_field.setFixedWidth(34)
        self.page_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_field.setMaxLength(12)  # o número ou o rótulo do PDF ("iv")
        self.page_field.returnPressed.connect(self._go_to_typed_page)
        self.page_total = QLabel()
        self.page_total.setProperty("ofRole", "help")
        layout.addWidget(prev_button)
        layout.addWidget(self.page_field)
        layout.addWidget(self.page_total)
        layout.addWidget(next_button)
        layout.addWidget(_separator())

        zoom_out_button = self._tool_button(build_zoom_out_icon(), "Diminuir zoom")
        zoom_out_button.clicked.connect(self._zoom_out)
        zoom_in_button = self._tool_button(build_zoom_in_icon(), "Aumentar zoom")
        zoom_in_button.clicked.connect(self._zoom_in)
        self.zoom_button = QToolButton()
        self.zoom_button.setObjectName("ZoomButton")
        self.zoom_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.zoom_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_button.setText(f"{int(self._scale * 100)}%")
        zoom_menu = QMenu(self.zoom_button)
        for percent in (50, 75, 100, 125, 150, 200, 400, 800):
            zoom_menu.addAction(f"{percent}%").triggered.connect(lambda _checked=False, p=percent: self._set_zoom(p))
        zoom_menu.addSeparator()
        self._zoom_fit_width_action = zoom_menu.addAction("")
        self._zoom_fit_width_action.triggered.connect(self._fit_width)
        self._zoom_fit_page_action = zoom_menu.addAction("")
        self._zoom_fit_page_action.triggered.connect(self._fit_page)
        self.zoom_button.setMenu(zoom_menu)
        layout.addWidget(zoom_out_button)
        layout.addWidget(self.zoom_button)
        layout.addWidget(zoom_in_button)

        # Ajuste (largura, página, girar) e modo de exibição: um botão com menu cada. O mesmo
        # menu serve ao "..." da janela estreita.
        self._more_actions = []
        fit_menu = QMenu(self)
        for handler, text in (
            (self._fit_width, "Ajustar à largura"),
            (self._fit_page, "Ajustar à página (Ctrl+0)"),
            (self._rotate_view, "Girar a visualização (o arquivo não muda)"),
        ):
            action = fit_menu.addAction("")
            action.triggered.connect(handler)
            self._more_actions.append((action, text))
        mode_menu = QMenu(self)
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_actions = {}
        for key, icon, text in (
            (CONTINUOUS, build_continuous_page_icon(), "Rolagem contínua"),
            (SINGLE, build_single_page_icon(), "Página única"),
            (DOUBLE, build_double_page_icon(), "Página dupla"),
            (BOOK, build_book_icon(), "Livro (capa sozinha)"),
        ):
            action = mode_menu.addAction(icon, "")
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, k=key: self.set_layout(k))
            self._mode_group.addAction(action)
            self._mode_actions[key] = action
            self._more_actions.append((action, text))
        self.single_page_action = self._mode_actions[SINGLE]
        self.continuous_action = self._mode_actions[CONTINUOUS]
        self.double_page_action = self._mode_actions[DOUBLE]
        self.book_action = self._mode_actions[BOOK]
        self.single_page_action.setChecked(True)

        self.fit_button = self._menu_button(build_fit_width_icon(), "Ajuste e rotação", fit_menu)
        self.mode_button = self._menu_button(build_single_page_icon(), "Modo de exibição", mode_menu)
        fit_separator, mode_separator = _separator(), _separator()
        layout.addWidget(fit_separator)
        layout.addWidget(self.fit_button)
        layout.addWidget(mode_separator)
        layout.addWidget(self.mode_button)
        self._view_widgets = [fit_separator, self.fit_button, mode_separator, self.mode_button]

        # Janela estreita: ajuste e modo juntos num menu só.
        self.more_button = self._tool_button(build_more_icon(), "Mais opções de exibição")
        self.more_button.setObjectName("MoreButton")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self.more_button)
        more_menu.addActions(fit_menu.actions())
        more_menu.addSeparator()
        more_menu.addActions(mode_menu.actions())
        self.more_button.setMenu(more_menu)
        self.more_button.hide()
        layout.addWidget(self.more_button)
        layout.addWidget(_separator())

        search_button = self._tool_button(build_search_icon(), "Buscar (Ctrl+F)")
        search_button.clicked.connect(self._toggle_search)
        layout.addWidget(search_button)
        self.hand_button = self._tool_button(build_hand_icon(), "Ferramenta de mão: arrastar a página (Ctrl+Shift+H)")
        self.hand_button.setCheckable(True)
        self.hand_button.clicked.connect(self.set_hand_mode)
        layout.addWidget(self.hand_button)
        layout.addStretch()

        # Escondido: a coluna da esquerda da aba de documento faz o papel dele.
        self.thumbnails_button = self._tool_button(build_thumbnails_icon(), "Painel lateral (miniaturas, marcadores, anexos)")
        self.thumbnails_button.setCheckable(True)
        self.thumbnails_button.setChecked(True)
        self.thumbnails_button.clicked.connect(self._toggle_thumbnails)
        layout.addWidget(self.thumbnails_button)

        self._document_dependent_widgets = [
            prev_button,
            next_button,
            zoom_out_button,
            zoom_in_button,
            self.zoom_button,
            self.fit_button,
            self.mode_button,
            self.page_field,
            self.more_button,
            self.thumbnails_button,
            search_button,
            self.hand_button,
        ]
        self._retranslate_toolbar_menus()
        return toolbar

    def _menu_button(self, icon, tooltip: str, menu: QMenu) -> QToolButton:
        """Ícone + seta, abrindo `menu` (ajuste, modo de exibição)."""
        button = self._tool_button(icon, tooltip)
        button.setObjectName("MenuButton")
        button.setFixedSize(44, 32)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        return button

    def _retranslate_toolbar_menus(self):
        self._zoom_fit_width_action.setText(tr("Ajustar à largura"))
        self._zoom_fit_page_action.setText(tr("Ajustar à página"))
        self.zoom_button.setToolTip(tr("Zoom"))
        self.zoom_button.setAccessibleName(tr("Zoom"))
        for action, text in self._more_actions:
            action.setText(tr(text))

    def set_compact(self, compact: bool) -> None:
        """Janela estreita: ajustes, girar e modos de exibição vão para o menu "..."."""
        for widget in self._view_widgets:
            widget.setVisible(not compact)
        self.more_button.setVisible(compact)

    def _tool_button(self, icon, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setProperty("ofRole", "icon")
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(32, 32)
        button.setToolTip(tr(tooltip))
        button.setAccessibleName(tr(tooltip))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._translatable_tooltips.append((button, tooltip))
        return button

    def _set_document_controls_enabled(self, enabled: bool):
        for widget in self._document_dependent_widgets:
            widget.setEnabled(enabled)

    # -- carregamento do documento -----------------------------------------

    def _retranslate_empty_state(self):
        self._empty_label.setText(tr("Nenhum documento aberto"))
        self._empty_hint.setText(tr("Arraste um PDF para cá ou escolha um arquivo no computador."))
        self._empty_open_button.setText(tr("Abrir arquivo..."))
        self._empty_recent_button.setText(tr("Recentes"))

    def _fill_recent_menu(self, menu: QMenu):
        menu.clear()
        recent = preferences().recent_files()
        for path in recent:
            action = menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self.open_path(p))
        if not recent:
            menu.addAction(tr("Nenhum arquivo recente")).setEnabled(False)

    def _browse_open(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), "", "PDF (*.pdf)")
        if path:
            self.open_path(path)

    def close_document(self):
        """Fecha o documento no pdfium (ao fechar a janela): no Windows, um arquivo aberto
        não pode ser apagado, e as versões temporárias do documento precisam sair."""
        if self._document is not None:
            self._save_reading_position()
            self.thumbnail_list.clear_document()
            with PDFIUM_LOCK:
                self._document.close()
            self._document = None

    def _save_reading_position(self):
        if self._position_path:
            preferences().set_reading_position(self._position_path, *self._view_position())

    def _reload(self):
        path = self.session.path()
        # Uma versão nova do mesmo documento (operação, desfazer, refazer) mantém a página e a
        # posição em que o usuário estava; outro documento abre onde a leitura parou ou onde o
        # próprio PDF pede.
        same_document = self.session.last_change() == "version"
        keep_view = self._view_position() if same_document and self._document is not None else None
        if not same_document and self._document is not None:
            self._save_reading_position()
        self._finish_field_edit(commit=False)
        self._form_widgets = []
        self._geometries = {}
        self._links, self._notes, self._hover_target, self._link_press = {}, {}, None, None
        self._page_names = {}
        self._stop_search()
        self._pending_scroll = None
        if self._document is not None:
            self.thumbnail_list.clear_document()
            with PDFIUM_LOCK:
                self._document.close()
            self._document = None

        if not path:
            self._show_empty_state()
            return

        document = self._open_document_with_password_prompt(path)
        if document is None:
            self._show_empty_state()
            return

        view = initial_view(path) if not same_document else None
        # O modo de exibição do PDF vale até o usuário escolher um (a escolha dele fica guardada).
        if view is not None and view.layout and preferences().page_layout() is None:
            self.set_layout(view.layout)

        self._document = document
        self._text_selection, self._selection_rects = None, {}
        # Um PDF anexado abre de um arquivo temporário, de outro nome a cada vez: nada a lembrar.
        self._position_path = None if self.session.needs_save_as() else self.session.source_path()
        if not same_document:
            self._view_rotation = 0  # outro documento começa sem rotação da tela
            self._back, self._forward = [], []
            self._next_field = None
        self._search = DocumentSearch(self._document)
        self._matches = []
        self._current_match = -1
        saved = preferences().reading_position(self._position_path) if view is not None and self._position_path else None
        position = keep_view or saved
        first_page = position[0] if position else (view.page if view is not None else 0)
        self._current_page = min(first_page, max(self._page_count() - 1, 0))
        if self._continuous and (self._current_page or position):
            self._pending_scroll = (self._current_page, position[1] if position else 0.0)
        self.search_bar.hide()
        self.annotation_state.clear_pending()
        self.redaction_state.clear_pending()
        self.measure_state.clear_result()

        self._set_document_controls_enabled(True)
        self.thumbnail_list.load_document(self._document)
        self.side_panel.load(path)
        self.side_panel.setVisible(self._show_thumbnails)
        if view is not None and view.panel:
            self.side_panel.show_panel(view.panel)
            self.show_side_panel(True)
        self._update_notices(path)
        self._form_widgets = self._load_form_widgets(path)
        self.content_stack.setCurrentIndex(1)
        self._rebuild_canvas()
        self._on_markup_state_changed()  # o modo do PDF não vale com uma ferramenta de desenho
        if keep_view is not None:
            if not self._continuous:
                self._show_view(self._current_page, keep_view[1])
            if self._next_field:
                self._layout_timer.start()
            return
        self._refit()
        if saved is not None:
            if not self._continuous:
                self._show_view(self._current_page, saved[1])
        elif view is not None and view.top is not None:
            self._show_destination(self._current_page, view.top)
        self.scroll_area.setFocus()  # as teclas de leitura valem logo ao abrir

    def _update_notices(self, path: str):
        if self.session.last_change() != "version":
            self._dismissed_notices = set()  # outro documento: os avisos voltam
        self._notices = document_notices(path)
        self._show_notices()

    def _show_notices(self):
        while self._notice_layout.count():
            item = self._notice_layout.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.verify_button = None
        shown = 0
        for kind, message in zip(self._notices.kinds, self._notices.messages):
            if kind in self._dismissed_notices:
                continue
            self._notice_layout.addWidget(self._notice_row(kind, tr_message(message)))
            shown += 1
        self.notice_bar.setVisible(shown > 0)

    def _notice_row(self, kind: str, text: str) -> QWidget:
        row = QFrame()
        row.setObjectName("documentNotice")
        row.setProperty("kind", kind)
        row.setFixedHeight(36)
        label = QLabel(text)
        label.setObjectName("NoticeText")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(8)
        layout.addWidget(label, 1)
        actions = {
            "signed": ("Ver", "Verificar as assinaturas", self.verify_signatures_requested),
            "protected": ("Remover senha", "Remover senha", self.remove_password_requested),
        }
        if kind in actions:
            text, tip, signal = actions[kind]
            button = QPushButton(tr(text))
            button.setProperty("ofVariant", "ghost")
            button.setProperty("ofSize", "mini")
            button.setToolTip(tr(tip))
            button.clicked.connect(signal)
            layout.addWidget(button)
            if kind == "signed":
                self.verify_button = button
        # Fora de _tool_button: a faixa é refeita a cada aviso, e a lista de dicas a traduzir
        # guardaria botões já apagados.
        close = QToolButton()
        close.setObjectName("NoticeClose")
        close.setProperty("ofRole", "icon")
        close.setIcon(build_close_icon())
        close.setIconSize(QSize(16, 16))
        close.setFixedSize(28, 28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip(tr("Fechar aviso"))
        close.setAccessibleName(tr("Fechar aviso"))
        close.clicked.connect(lambda _checked=False, k=kind: self._dismiss_notice(k))
        layout.addWidget(close)
        return row

    def _dismiss_notice(self, kind: str):
        self._dismissed_notices.add(kind)
        self._show_notices()

    def _show_empty_state(self):
        self.content_stack.setCurrentIndex(0)
        self.side_panel.clear()
        self.side_panel.hide()
        self.notice_bar.hide()
        self._set_document_controls_enabled(False)
        self._update_page_indicator()

    def _page_count(self) -> int:
        if self._document is None:
            return 0
        with PDFIUM_LOCK:
            return len(self._document)

    def _open_document_with_password_prompt(self, path: str):
        """Abre o PDF em `path`, pedindo a senha ao usuário se estiver protegido.

        Tenta antes a senha já digitada para esse arquivo nesta sessão (o resultado de uma
        ferramenta aplicada a um PDF protegido, ou o mesmo arquivo reaberto). Repete o
        prompt em caso de senha errada, até o usuário acertar ou cancelar. Para qualquer
        outro tipo de falha (arquivo corrompido, formato inválido) mostra um erro e desiste
        sem pedir senha nenhuma. Retorna None se não foi possível abrir o PDF.
        """
        password = known_password(path)
        prompted = False
        while True:
            try:
                with PDFIUM_LOCK:
                    document = pdfium.PdfDocument(path, password=password)
                    # Sem isso, carimbos de assinatura e campos de formulário (AcroForm) não
                    # aparecem no render: draw_annots=True sozinho não é suficiente para
                    # widgets de formulário.
                    document.init_forms()
                if password:
                    # As ferramentas (pypdf) passam a abrir o arquivo com a mesma senha,
                    # sem pedir de novo; a senha só fica na memória desta sessão.
                    remember_password(path, password)
                return document
            except pdfium.PdfiumError as exc:
                if exc.err_code != pdfium.raw.FPDF_ERR_PASSWORD:
                    show_error(self, tr("Abrir PDF"), tr("Não foi possível abrir o PDF: {error}"), exc)
                    return None

                prompt = (
                    tr("Senha incorreta. Tente novamente:")
                    if prompted
                    else tr("Este PDF está protegido por senha. Digite a senha para abri-lo:")
                )
                entered, ok = QInputDialog.getText(
                    self, tr("PDF protegido por senha"), prompt, QLineEdit.EchoMode.Password
                )
                if not ok:
                    return None
                password = entered
                prompted = True
            except Exception as exc:
                show_error(self, tr("Abrir PDF"), tr("Não foi possível abrir o PDF: {error}"), exc)
                return None

    # -- renderização --------------------------------------------------------

    def _rebuild_canvas(self):
        self._finish_field_edit()
        self._rendered_pages = set()
        self._page_labels = []
        self._page_tops = []

        if self._continuous:
            container = QWidget()
            vlayout = QVBoxLayout(container)
            margin, spacing = 12, 12
            vlayout.setContentsMargins(margin, margin + self._top_inset, margin, margin)
            vlayout.setSpacing(spacing)

            offset = margin + self._top_inset
            for row in self._rows():
                labels = [self._make_placeholder_label(index) for index in row]
                if self._spread:
                    vlayout.addWidget(self._spread_row(row, labels), 0, Qt.AlignmentFlag.AlignHCenter)
                else:
                    vlayout.addWidget(labels[0], 0, Qt.AlignmentFlag.AlignHCenter)
                for label in labels:
                    self._page_labels.append(label)
                    self._page_tops.append(offset)
                offset += max(label.height() for label in labels) + spacing
            vlayout.addStretch()

            self.scroll_area.setWidget(container)
            self._update_visible_pages()
        else:
            label = PageCanvas()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setContentsMargins(0, self._top_inset, 0, 0)
            label.mouse_pressed.connect(self._on_canvas_pressed)
            label.mouse_moved.connect(self._on_canvas_moved)
            label.mouse_released.connect(self._on_canvas_released)
            label.mouse_double_clicked.connect(self._on_canvas_double_clicked)
            label.mouse_triple_clicked.connect(self._on_canvas_triple_clicked)
            label.mouse_hovered.connect(
                lambda x, y, canvas=label: self._on_page_hovered(canvas, self._current_page, x, y)
            )
            self._page_labels = [label]
            self.scroll_area.setWidget(label)
            self._show_single_page(self._current_page)
            self._update_canvas_cursor()

        self._update_page_indicator()

    def _rows(self) -> list[list[int]]:
        """As páginas de cada linha da rolagem: uma por linha, ou duas na página dupla (1-2,
        3-4...) e no livro (1 sozinha, depois 2-3, 4-5...), contando de 1."""
        pages = list(range(self._page_count()))
        if not self._spread:
            return [[page] for page in pages]
        start = 1 if self._spread == BOOK else 0
        rows = [[0]] if start and pages else []
        rows += [pages[i : i + 2] for i in range(start, len(pages), 2)]
        return rows

    def _spread_row(self, row: list[int], labels: list[QLabel]) -> QWidget:
        """Duas páginas lado a lado, encostadas no meio como um livro aberto. Página que fica
        sozinha na linha (a capa do livro, a última) fica do lado em que estaria impressa."""
        widget = QWidget()
        hlayout = QHBoxLayout(widget)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(_PAGE_GAP // 2)
        if len(labels) == 1:
            spacer = QWidget()
            spacer.setFixedSize(labels[0].width(), 1)
            on_the_right = self._spread == BOOK and row[0] % 2 == 0  # ímpar contando de 1
            pair: list[QWidget] = [spacer, labels[0]] if on_the_right else [labels[0], spacer]
        else:
            pair = list(labels)
        for item, side in zip(pair, (Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft)):
            hlayout.addWidget(item, 0, side | Qt.AlignmentFlag.AlignTop)
        return widget

    def _row_of(self, page: int) -> list[int]:
        return next((row for row in self._rows() if page in row), [page])

    def _make_placeholder_label(self, index: int) -> QLabel:
        geometry = self._geometry(index)
        width_pt, height_pt = geometry.width, geometry.height
        # Na rolagem a página não tem ferramentas de desenho (elas passam para a página única),
        # mas tudo o que é de leitura funciona: links, seleção de texto, notas e formulários.
        label = PageCanvas()
        label.setFixedSize(max(1, int(width_pt * self._scale)), max(1, int(height_pt * self._scale)))
        label.setStyleSheet("background-color: white;")
        label.setCursor(self._canvas_cursor())
        label.mouse_hovered.connect(lambda x, y, canvas=label: self._on_page_hovered(canvas, index, x, y))
        label.mouse_pressed.connect(lambda x, y, canvas=label: self._on_scroll_page_pressed(canvas, index, x, y))
        label.mouse_moved.connect(lambda x, y, canvas=label: self._extend_selection(canvas, x, y))
        label.mouse_released.connect(lambda x, y, canvas=label: self._finish_selection(canvas, index, x, y))
        label.mouse_double_clicked.connect(lambda x, y: self._on_scroll_page_clicked_again(index, x, y, word_range))
        label.mouse_triple_clicked.connect(lambda x, y: self._on_scroll_page_clicked_again(index, x, y, line_range))
        return label

    def _render_with_overlays(self, index: int) -> QPixmap:
        with PDFIUM_LOCK:
            assert self._document is not None
            page = self._document[index]
            pixmap = render_page(page, self._scale, self.devicePixelRatioF(), rotation=self._view_rotation)
            page.close()
        pixmap = self._with_form_fields(pixmap, index)
        pixmap = self._with_highlight(pixmap, index)
        pixmap = self._with_pending_annotations(pixmap, index)
        pixmap = self._with_pending_redactions(pixmap, index)
        pixmap = self._with_picked_areas(pixmap, index)
        return self._with_measure_overlay(pixmap, index)

    def _show_single_page(self, index: int):
        if self._document is None or not (0 <= index < self._page_count()):
            return
        self._finish_field_edit()  # o editor fica sobre a página: grava antes de trocá-la
        self._current_page = index
        pixmap = self._render_with_overlays(index)
        self._page_labels[0].setPixmap(pixmap)
        self._page_labels[0].resize(logical_size(pixmap))
        self._apply_selection(index, self._page_labels[0])
        self.thumbnail_list.select_page(index)
        self._update_page_indicator()

    def _render_page_into_label(self, index: int, label: QLabel):
        label.setPixmap(self._render_with_overlays(index))
        self._rendered_pages.add(index)
        self._apply_selection(index, label)

    def _release_page(self, index: int):
        self._page_labels[index].clear()
        self._rendered_pages.discard(index)

    def _with_highlight(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        """Todas as ocorrências da busca na página, e a atual em destaque (antes só a atual
        aparecia)."""
        on_page = [(n, m) for n, m in enumerate(self._matches) if m.page_index == page_index]
        if not on_page:
            return pixmap

        highlighted = QPixmap(pixmap)
        painter = QPainter(highlighted)
        painter.setPen(Qt.PenStyle.NoPen)
        for number, match in on_page:
            painter.setBrush(_CURRENT_MATCH_COLOR if number == self._current_match else _HIGHLIGHT_COLOR)
            painter.drawRect(
                self._user_rect_to_screen(page_index, (match.left, match.bottom, match.right, match.top))
            )
        painter.end()
        return highlighted

    # Tudo o que o visualizador guarda (anotações, áreas de redação, medições, ocorrências da
    # busca) fica no espaço do usuário do PDF — o mesmo do pdfium e das operações de core/.
    # A conversão de/para pixels passa sempre pela geometria da página, que considera
    # /Rotate e CropBox (ver core/geometry.py).

    def _page_geometry(self, page_index: int) -> PageGeometry:
        """A geometria da página como está no arquivo."""
        geometry = self._geometries.get(page_index)
        if geometry is None:
            with PDFIUM_LOCK:
                assert self._document is not None
                page = self._document[page_index]
                geometry = PageGeometry.from_pdfium_page(page)
                page.close()
            self._geometries[page_index] = geometry
        return geometry

    def _geometry(self, page_index: int) -> PageGeometry:
        """A geometria da página como aparece na tela, com a rotação da visualização somada
        à `/Rotate` da página: toda conversão entre tela e PDF passa por aqui, então cliques,
        marcações e destaques continuam no lugar com a página girada."""
        geometry = self._page_geometry(page_index)
        if not self._view_rotation:
            return geometry
        return dataclasses.replace(geometry, rotation=(geometry.rotation + self._view_rotation) % 360)

    def _user_rect_to_screen(self, page_index: int, rect) -> QRectF:
        return QRectF(*self._geometry(page_index).user_rect_to_screen(rect, self._scale))

    def _with_pending_annotations(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        specs = [s for s in self.annotation_state.pending() if s.page_index == page_index]
        comment = self.annotation_state.selected_comment()
        if comment is not None and (comment[0] != page_index or not self.annotation_state.is_page_active()):
            comment = None
        if not specs and comment is None:
            return pixmap

        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for spec in specs:
            self._paint_pending_spec(painter, page_index, spec)
            outline = QPen(QColor(PENDING_OUTLINE), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(outline)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._user_rect_to_screen(page_index, spec_rect(spec)).adjusted(-3, -3, 3, 3), 2, 2)
        if comment is not None:  # a escolhida na lista: um anel de 2 px no acento
            painter.setPen(QPen(theme.color("accent"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._user_rect_to_screen(page_index, comment[1]).adjusted(-4, -4, 4, 4), 3, 3)
        painter.end()
        return result

    def _paint_pending_spec(self, painter: QPainter, page_index: int, spec: AnnotationSpec):
        color = QColor(f"#{spec.color}")

        if spec.kind in ("highlight", "underline", "strikeout"):
            for quad in spec.quads:
                rect = self._user_rect_to_screen(page_index, quad)
                if spec.kind == "highlight":
                    painter.setPen(Qt.PenStyle.NoPen)
                    fill = QColor(color)
                    fill.setAlpha(110)
                    painter.setBrush(fill)
                    painter.drawRect(rect)
                elif spec.kind == "underline":
                    painter.setPen(QPen(color, 2))
                    painter.drawLine(rect.bottomLeft(), rect.bottomRight())
                else:  # strikeout
                    painter.setPen(QPen(color, 2))
                    mid_y = rect.center().y()
                    painter.drawLine(QPointF(rect.left(), mid_y), QPointF(rect.right(), mid_y))
        elif spec.kind == "ink":
            self._paint_ink_stroke(painter, page_index, spec.points, color, spec.width)
        elif spec.kind in _SHAPE_TOOLS:
            self._paint_shape(painter, page_index, spec, color)
        elif spec.kind == "note":
            rect = self._user_rect_to_screen(page_index, spec_rect(spec))
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.setBrush(color)
            painter.drawRect(rect)
        elif spec.kind == "stamp":
            rect = self._user_rect_to_screen(page_index, spec_rect(spec))
            painter.setPen(QPen(color, 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRect(rect)
            painter.setPen(color)
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(max(1, round(STAMP_FONT_SIZE * spec.scale * self._scale)))  # cresce com a caixa
            painter.setFont(font)
            margin = 8 * spec.scale * self._scale  # como na aparência gravada (core/annotations.py)
            painter.drawText(rect.adjusted(margin, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, spec.text)

    def _with_pending_redactions(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        rects = [r for r in self.redaction_state.pending() if r.page_index == page_index]
        if not rects:
            return pixmap

        selected = self.redaction_state.selected()
        result = QPixmap(pixmap)
        painter = QPainter(result)
        for rect in rects:
            screen_rect = self._user_rect_to_screen(page_index, rect.as_rect())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 200))
            painter.drawRect(screen_rect)
            if rect == selected:
                painter.setPen(QPen(QColor("#ff5252"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(screen_rect.adjusted(-3, -3, 3, 3))
        painter.end()
        return result

    def _with_picked_areas(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        """Áreas marcadas para a edição de texto (só com a ferramenta ativa)."""
        if not self.area_pick_state.is_page_active():
            return pixmap
        areas = [(n, rect) for n, (page, rect) in enumerate(self.area_pick_state.areas()) if page == page_index]
        if not areas:
            return pixmap
        selected = self.area_pick_state.selected()
        result = QPixmap(pixmap)
        painter = QPainter(result)
        for number, rect in areas:
            color = QColor("#ff5252") if number == selected else QColor("#2f80ed")
            self._paint_picked_area(painter, page_index, rect, number, color)
        painter.end()
        return result

    @staticmethod
    def _drag_rect(start_pdf, end_pdf) -> tuple[float, float, float, float]:
        (x1, y1), (x2, y2) = start_pdf, end_pdf
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def _paint_picked_area(self, painter: QPainter, page_index: int, rect, number: int | None, color: QColor):
        """Uma área marcada (ou sendo arrastada, com `number` None): o conteúdo que a aba
        desenhar e o contorno tracejado, numerado."""
        screen_rect = self._user_rect_to_screen(page_index, rect).normalized()
        preview = self.area_pick_state.preview()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 15 if preview else 40))
        painter.drawRect(screen_rect)
        if preview is not None:
            painter.save()
            preview(painter, screen_rect, number)
            painter.restore()
        painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(screen_rect)
        if number is not None:
            painter.setPen(color)
            painter.drawText(screen_rect.adjusted(3, 2, 0, 0), str(number + 1))

    def _on_picked_areas_changed(self):
        """Mostra a página da área escolhida na tabela da aba Editar."""
        selected = self.area_pick_state.selected()
        areas = self.area_pick_state.areas()
        if (
            self._document is not None
            and selected is not None
            and 0 <= selected < len(areas)
            and 0 <= areas[selected][0] < self._page_count()
            and areas[selected][0] != self._current_page
            and not self._continuous
        ):
            self._show_single_page(areas[selected][0])
            return
        self._refresh_current_render()

    def _with_measure_overlay(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        segment = self.measure_state.last_segment()
        if segment is None or segment[0] != page_index:
            return pixmap

        _, start_pdf, end_pdf = segment
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_measure_segment(painter, page_index, start_pdf, end_pdf)
        painter.end()
        return result

    def _paint_measure_segment(self, painter: QPainter, page_index: int, start_pdf, end_pdf):
        start_widget = self._pdf_point_to_widget(page_index, *start_pdf)
        end_widget = self._pdf_point_to_widget(page_index, *end_pdf)
        color = QColor("#ff5252")

        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.drawLine(start_widget, end_widget)
        painter.setBrush(color)
        for point in (start_widget, end_widget):
            painter.drawEllipse(point, 3, 3)

        dx = end_pdf[0] - start_pdf[0]
        dy = end_pdf[1] - start_pdf[1]
        distance_pt = (dx**2 + dy**2) ** 0.5
        label = format_distance(distance_pt, self.measure_state.unit())
        midpoint = QPointF((start_widget.x() + end_widget.x()) / 2, (start_widget.y() + end_widget.y()) / 2)

        painter.setPen(QPen(QColor("#000000")))
        text_rect = QRectF(midpoint.x() - 40, midpoint.y() - 22, 80, 16)
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(text_rect)
        painter.setPen(QPen(color))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _pdf_point_to_widget(self, page_index: int, x_pdf: float, y_pdf: float) -> QPointF:
        return QPointF(*self._geometry(page_index).user_to_screen(x_pdf, y_pdf, self._scale))

    def _paint_shape(self, painter: QPainter, page_index: int, spec: AnnotationSpec, color: QColor):
        pen = QPen(color, max(1.0, spec.width * self._scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if spec.kind == "arrow":
            start = self._pdf_point_to_widget(page_index, *spec.points[0])
            end = self._pdf_point_to_widget(page_index, *spec.points[-1])
            painter.drawLine(start, end)
            for x, y in arrow_head(spec.points[0], spec.points[-1], spec.width):
                painter.drawLine(self._pdf_point_to_widget(page_index, x, y), end)
            return
        rect = self._user_rect_to_screen(page_index, spec_rect(spec))
        if spec.kind == "square":
            painter.drawRect(rect)
        else:
            painter.drawEllipse(rect)

    def _paint_ink_stroke(self, painter: QPainter, page_index: int, points, color: QColor, width: float = 2.5):
        pen = QPen(color, max(1.0, width * self._scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        polyline = QPolygonF([self._pdf_point_to_widget(page_index, x, y) for x, y in points])
        painter.drawPolyline(polyline)

    def _update_visible_pages(self):
        if not self._continuous or self._document is None or not self._page_labels:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        viewport_top = scrollbar.value()
        viewport_height = self.scroll_area.viewport().height()
        viewport_bottom = viewport_top + viewport_height
        buffer = viewport_height
        keep = viewport_height * _KEEP_RENDERED_SCREENS

        current_page = 0
        for index, label in enumerate(self._page_labels):
            label_top = self._page_tops[index]
            label_bottom = label_top + label.height()
            if label_top <= viewport_top and (index == 0 or self._page_tops[index - 1] != label_top):
                current_page = index  # na página dupla, a primeira da linha
            if label_bottom >= viewport_top - buffer and label_top <= viewport_bottom + buffer:
                if index not in self._rendered_pages:
                    self._render_page_into_label(index, label)
            elif index in self._rendered_pages and (
                label_bottom < viewport_top - keep or label_top > viewport_bottom + keep
            ):
                self._release_page(index)
        if scrollbar.maximum() > 0 and viewport_top >= scrollbar.maximum():
            # No fim da rolagem a última linha não chega ao topo: ela é a atual (senão
            # "próxima" e o indicador ficariam presos na penúltima).
            current_page = self._page_tops.index(self._page_tops[-1])

        self._current_page = current_page
        self.thumbnail_list.select_page(current_page)
        self._update_page_indicator()

    def _scroll_to_page(self, index: int, fraction: float = 0.0):
        if not 0 <= index < len(self._page_tops):
            return
        target = self._page_tops[index] + int(fraction * self._page_labels[index].height())
        scrollbar = self.scroll_area.verticalScrollBar()
        if target > scrollbar.maximum():
            # O layout novo ainda não foi aplicado (logo depois de zoom ou troca de modo):
            # a rolagem acontece quando a faixa da barra crescer (`_apply_pending_scroll`).
            self._pending_scroll = (index, fraction)
        else:
            self._pending_scroll = None
        scrollbar.setValue(target)

    def _apply_pending_scroll(self, _minimum: int, _maximum: int):
        if self._pending_scroll is not None and self._continuous:
            self._scroll_to_page(*self._pending_scroll)

    def _scroll_anchor(self) -> tuple[int, float]:
        """Página no topo da área visível e quanto dela já passou (0 a 1)."""
        if not self._continuous or not self._page_tops:
            return self._current_page, 0.0
        if self._pending_scroll is not None:
            return self._pending_scroll
        value = self.scroll_area.verticalScrollBar().value()
        index = self._current_page
        height = max(1, self._page_labels[index].height())
        return index, min(1.0, max(0.0, (value - self._page_tops[index]) / height))

    def _update_page_indicator(self):
        self.session.set_current_page(self._current_page)
        if self._document is None:
            self.page_field.setText("")
            self.page_total.setText("")
            return
        self.page_field.setText(str(self._current_page + 1))
        total = tr("de {total}").format(total=self._page_count())
        name = self._page_name(self._current_page)  # "iv": o número impresso, se o PDF tiver
        self.page_total.setText(f"{total} ({name})" if name and name != str(self._current_page + 1) else total)
        tip = (
            tr("Página {current} de {total}").format(current=self._current_page + 1, total=self._page_count())
            + " — " + tr("Ir para a página... (Ctrl+G)")
        )
        self.page_field.setToolTip(tip)
        self.page_field.setAccessibleName(tip)

    def _page_name(self, index: int) -> str:
        name = self._page_names.get(index)
        if name is None:
            try:
                with PDFIUM_LOCK:
                    assert self._document is not None
                    name = self._document.get_page_label(index)
            except Exception:
                name = ""  # um rótulo malformado não impede de ver a página
            self._page_names[index] = name
        return name

    def _go_to_typed_page(self):
        text = self.page_field.text().strip()
        if text.isdigit():
            self._jump_to_page(int(text) - 1)
        elif text:  # o rótulo do PDF, como "iv"
            page = next((i for i in range(self._page_count()) if self._page_name(i).lower() == text.lower()), None)
            if page is not None:
                self._jump_to_page(page)
        self._update_page_indicator()  # sem página que sirva: volta ao número da página atual

    # -- navegação e zoom -----------------------------------------------------

    def _go_prev(self):
        if self._spread:
            self._step_row(-1)
        elif self._continuous:
            self._scroll_to_page(max(0, self._current_page - 1))
        else:
            self._show_single_page(max(0, self._current_page - 1))
            self._scroll_single_to(0)

    def _go_next(self):
        if self._document is None:
            return
        last = self._page_count() - 1
        if self._spread:
            self._step_row(1)
        elif self._continuous:
            self._scroll_to_page(min(last, self._current_page + 1))
        else:
            self._show_single_page(min(last, self._current_page + 1))
            self._scroll_single_to(0)

    def _step_row(self, direction: int):
        """Na página dupla, avança ou volta uma linha (duas páginas)."""
        rows = self._rows()
        current = next((n for n, row in enumerate(rows) if self._current_page in row), 0)
        self._scroll_to_page(rows[max(0, min(len(rows) - 1, current + direction))][0])

    def _go_first(self):
        self._jump_to_page(0)

    def _go_last(self):
        if self._document is not None:
            self._jump_to_page(self._page_count() - 1)

    def _screen_step(self) -> int:
        return max(_LINE_STEP, self.scroll_area.viewport().height() - _SCREEN_OVERLAP)

    def _scroll_view(self, direction: int, step: int):
        """Desce ou sobe `step` pixels; na página única, passada a borda, vira a página."""
        if self._document is None:
            return
        bar = self.scroll_area.verticalScrollBar()
        at_edge = bar.value() >= bar.maximum() if direction > 0 else bar.value() <= bar.minimum()
        if at_edge and not self._continuous:
            self._flip_page(direction)
        else:
            bar.setValue(bar.value() + direction * step)

    def _flip_page(self, direction: int) -> bool:
        """Vira a página única continuando a leitura: descendo, do alto da seguinte; subindo,
        do fim da anterior. False se não há página para aquele lado."""
        page = self._current_page + direction
        if not 0 <= page < self._page_count():
            return False
        self._show_single_page(page)
        self._scroll_single_to(0 if direction > 0 else -1)
        return True

    def _scroll_single_to(self, value: int):
        """Rola a página única até `value` (-1: o fim). A faixa da barra só acompanha uma página
        de outro tamanho depois do layout, então a rolagem é repetida logo em seguida."""
        self._single_scroll = value
        self._apply_single_scroll()
        self._layout_timer.start()

    def _after_layout(self):
        self._apply_single_scroll()
        self._single_scroll = None
        self._apply_zoom_anchor()
        if self._next_field:
            self._open_next_field()

    def _apply_single_scroll(self):
        if self._single_scroll is None or self._continuous:
            return
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum() if self._single_scroll < 0 else self._single_scroll)

    # -- histórico de navegação ---------------------------------------------------

    def _view_position(self) -> tuple[int, float]:
        """A página em que se está e quanto dela já passou no alto da tela (0 a 1)."""
        if self._continuous:
            return self._scroll_anchor()
        canvas = self._page_labels[0] if self._page_labels else None
        height = max(1, canvas.height()) if canvas is not None else 1
        return self._current_page, self.scroll_area.verticalScrollBar().value() / height

    def _show_view(self, page: int, fraction: float):
        page = max(0, min(self._page_count() - 1, page))
        if self._continuous:
            self._scroll_to_page(page, fraction)
        else:
            self._show_single_page(page)
            self._scroll_single_to(int(fraction * max(1, self._page_labels[0].height())))

    def _remember_view(self):
        """Antes de um salto (link, marcador, miniatura, ir para a página, busca): é para cá que
        Voltar traz. Virar a página e rolar não entram, como nos leitores de PDF."""
        if self._document is None or not self._page_labels:
            return
        position = self._view_position()
        if not self._back or self._back[-1] != position:
            self._back.append(position)
            del self._back[:-_HISTORY_LIMIT]
        self._forward.clear()

    def go_back(self):
        self._step_history(self._back, self._forward)

    def go_forward(self):
        self._step_history(self._forward, self._back)

    def _step_history(self, source: list[tuple[int, float]], target: list[tuple[int, float]]):
        if self._document is None or not source:
            return
        target.append(self._view_position())
        self._show_view(*source.pop())

    def _jump_to_page(self, index: int):
        if self._document is None:
            return
        self._remember_view()
        self._go_to_page(index)
        if not self._continuous:
            self._scroll_single_to(0)

    def _jump_to_destination(self, page: int, top: float | None):
        """Um link ou marcador: a página e, se o destino disser, a altura certa nela."""
        if self._document is None or not 0 <= page < self._page_count():
            return
        self._remember_view()
        self._show_destination(page, top)

    def _show_destination(self, page: int, top: float | None):
        y = 0.0
        if top is not None:
            geometry = self._geometry(page)
            _x, y = geometry.user_to_screen(geometry.width / 2, top, self._scale)
            y = max(0.0, y - _LINK_TARGET_MARGIN)
        if self._continuous:
            height = max(1, self._page_labels[page].height())
            self._scroll_to_page(page, min(1.0, y / height))
            return
        self._show_single_page(page)
        canvas = self._page_labels[0]
        offset = canvas.pixmap_offset().y() if isinstance(canvas, PageCanvas) else 0.0
        self._scroll_single_to(int(offset + y))

    def set_top_inset(self, inset: int) -> None:
        """Margem extra acima da página, para a barra de marcação não cobri-la."""
        if inset == self._top_inset:
            return
        self._top_inset = inset
        if self._document is None or not self._page_labels:
            return
        if self._continuous:
            self._apply_zoom()  # reconstrói mantendo a página e a posição
        else:
            self._page_labels[0].setContentsMargins(0, inset, 0, 0)
            self._show_single_page(self._current_page)

    def _go_to_page(self, index: int):
        if self._document is None:
            return
        index = max(0, min(self._page_count() - 1, index))
        if self._continuous:
            self._scroll_to_page(index)
        else:
            self._show_single_page(index)

    def _ask_go_to_page(self):
        if self._document is None:
            return
        number, ok = QInputDialog.getInt(
            self,
            tr("Ir para a página"),
            tr("Página (1 a {total}):").format(total=self._page_count()),
            self._current_page + 1,
            1,
            self._page_count(),
        )
        if ok:
            self._jump_to_page(number - 1)

    def _fit_page(self):
        """Zoom para a página inteira caber na área visível (e continuar cabendo se a janela
        mudar de tamanho, até o usuário escolher outro zoom)."""
        if self._document is None:
            return
        width, height = self._row_size(self._current_page)
        if width <= 0 or height <= 0:
            return
        self._fit = "page"
        viewport = self.scroll_area.viewport()
        self._set_fit_scale(min((viewport.width() - 24) / width, (viewport.height() - 24) / height))

    def _set_fit_scale(self, scale: float):
        scale = max(_MIN_SCALE, min(_MAX_SCALE, scale))
        if abs(scale - self._scale) >= 0.005:  # refazer a tela à toa perderia a posição
            self._scale = scale
            self._apply_zoom()

    def _refit(self):
        if self._fit == "width":
            self._fit_width()
        elif self._fit == "page":
            self._fit_page()

    def _rotate_view(self):
        """Gira a página na tela em 90° (para ler um escaneado de lado); o arquivo não muda
        — para girar de verdade, use a aba Páginas."""
        if self._document is None:
            return
        self._view_rotation = (self._view_rotation + 90) % 360
        page = self._current_page
        self._rebuild_canvas()
        self._go_to_page(page)
        self._refit()

    def eventFilter(self, watched, event):
        kind = event.type()
        if self._field_editor is not None and watched is self._field_editor[0]:
            # A caixa de várias linhas não tem "editingFinished": grava ao perder o foco, com as
            # mesmas exceções do campo de uma linha.
            if kind == QEvent.Type.FocusOut and event.reason() not in (
                Qt.FocusReason.PopupFocusReason,
                Qt.FocusReason.ActiveWindowFocusReason,
            ):
                self._finish_field_edit()
            return False
        if watched is self.scroll_area:
            if kind == QEvent.Type.Resize and self._fit:
                self._fit_timer.start()
            return False
        if self._document is None:
            return super().eventFilter(watched, event)
        if kind == QEvent.Type.Wheel:
            # Ctrl + roda do mouse: zoom (como nos leitores de PDF), em vez de rolar.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.angleDelta().y() > 0:
                    self._zoom_around(event.position(), self._zoom_in)
                elif event.angleDelta().y() < 0:
                    self._zoom_around(event.position(), self._zoom_out)
                return True
            return self._wheel_turns_page(event.angleDelta().y())
        if kind == QEvent.Type.ContextMenu:
            menu = self._context_menu(event.globalPos())
            menu.exec(event.globalPos())
            menu.deleteLater()
            return True
        if kind == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.BackButton:
                self.go_back()
                return True
            if event.button() == Qt.MouseButton.ForwardButton:
                self.go_forward()
                return True
            if event.button() == Qt.MouseButton.MiddleButton:
                self._pan_from = event.globalPosition()
                QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
                return True
        if self._pan_from is not None and event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.MiddleButton:
                self._pan_to(event.globalPosition())
                return True
            if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton:
                self._pan_from = None
                QApplication.restoreOverrideCursor()
                return True
        return super().eventFilter(watched, event)

    def _pan_to(self, global_point: QPointF):
        if self._pan_from is None:
            return
        moved = global_point - self._pan_from
        self._pan_from = global_point
        self._pan_travel += moved.manhattanLength()
        horizontal = self.scroll_area.horizontalScrollBar()
        vertical = self.scroll_area.verticalScrollBar()
        horizontal.setValue(horizontal.value() - int(moved.x()))
        vertical.setValue(vertical.value() - int(moved.y()))

    def set_hand_mode(self, enabled: bool):
        """A ferramenta de mão: arrastar move a página. Links e campos continuam com o clique."""
        self._hand_mode = enabled
        self.hand_button.setChecked(enabled)
        self._update_canvas_cursor()

    def _wheel_turns_page(self, delta: int) -> bool:
        """Na página única, a roda passada a borda da página vira a página, como a rolagem
        contínua faria. Trackpads mandam passos pequenos: vira a cada dente acumulado."""
        if self._continuous or not delta or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return False
        direction = -1 if delta > 0 else 1
        bar = self.scroll_area.verticalScrollBar()
        if not (bar.value() >= bar.maximum() if direction > 0 else bar.value() <= bar.minimum()):
            self._wheel_rest = 0
            return False
        self._wheel_rest += delta
        if abs(self._wheel_rest) < _WHEEL_NOTCH:
            return True
        self._wheel_rest = 0
        return self._flip_page(direction)

    def _zoom_around(self, point: QPointF, zoom):
        """Muda o zoom mantendo sob o mouse o ponto da página que estava sob ele."""
        content = self.scroll_area.widget()
        x = (self.scroll_area.horizontalScrollBar().value() + point.x()) / max(1, content.width())
        y = (self.scroll_area.verticalScrollBar().value() + point.y()) / max(1, content.height())
        zoom()
        self._zoom_anchor = (x, y, point)
        self._layout_timer.start()

    def _apply_zoom_anchor(self):
        anchor, self._zoom_anchor = self._zoom_anchor, None
        content = self.scroll_area.widget()
        if anchor is None or content is None:
            return
        x, y, point = anchor
        self._pending_scroll = None
        self.scroll_area.horizontalScrollBar().setValue(int(x * content.width() - point.x()))
        self.scroll_area.verticalScrollBar().setValue(int(y * content.height() - point.y()))

    def _context_menu(self, global_point) -> QMenu:
        """O botão direito na página. Quem chama abre o menu."""
        menu = QMenu(self)
        page, x, y = self._page_at(global_point)
        link = self._link_at(page, x, y)
        if link is not None:
            menu.addAction(tr("Abrir link") if link.url else self._link_tip(link)).triggered.connect(
                lambda _checked=False: self._follow_link(link)
            )
            if link.url:
                address = link.url[len("mailto:") :] if link.url.lower().startswith("mailto:") else link.url
                menu.addAction(tr("Copiar endereço do link")).triggered.connect(
                    lambda _checked=False: QApplication.clipboard().setText(address)
                )
            menu.addSeparator()
        allowed = self._copy_allowed()
        copy = menu.addAction(tr("Copiar") if allowed else tr("Copiar (bloqueado pelo autor)"))
        copy.setEnabled(allowed and self._text_selection is not None)
        copy.triggered.connect(self.copy_selected_text)
        menu.addAction(tr("Selecionar tudo")).triggered.connect(self.select_all_text)
        menu.addSeparator()
        back = menu.addAction(tr("Voltar"))
        back.setEnabled(bool(self._back))
        back.triggered.connect(self.go_back)
        forward = menu.addAction(tr("Avançar"))
        forward.setEnabled(bool(self._forward))
        forward.triggered.connect(self.go_forward)
        menu.addSeparator()
        hand = menu.addAction(tr("Ferramenta de mão"))
        hand.setCheckable(True)
        hand.setChecked(self._hand_mode)
        hand.triggered.connect(self.set_hand_mode)
        for text, handler in (
            ("Aumentar zoom", self._zoom_in),
            ("Diminuir zoom", self._zoom_out),
            ("Ajustar à largura", self._fit_width),
            ("Ajustar à página", self._fit_page),
            ("Girar a visualização (o arquivo não muda)", self._rotate_view),
        ):
            menu.addAction(tr(text)).triggered.connect(lambda _checked=False, h=handler: h())
        return menu

    def _page_at(self, global_point) -> tuple[int, float, float]:
        """A página sob um ponto da tela e a posição nela. Na rolagem, um ponto no vão ou além
        das páginas conta para a mais próxima (é o que um arrasto de seleção precisa)."""
        if not self._continuous or not self._page_tops:
            canvas = self._page_labels[0]
            point = canvas.mapFromGlobal(QPointF(global_point))
            offset = canvas.pixmap_offset() if isinstance(canvas, PageCanvas) else QPointF(0, 0)
            return self._current_page, point.x() - offset.x(), point.y() - offset.y()
        content = self.scroll_area.widget()
        inside = content.mapFromGlobal(QPointF(global_point))
        page = max(0, bisect.bisect_right(self._page_tops, inside.y()) - 1)  # a última da linha
        label_x = self._page_labels[page].mapTo(content, QPoint(0, 0)).x()
        if page > 0 and self._page_tops[page - 1] == self._page_tops[page] and inside.x() < label_x:
            page -= 1
        corner = self._page_labels[page].mapTo(content, QPoint(0, 0))
        return page, inside.x() - corner.x(), inside.y() - corner.y()

    def _set_zoom(self, percent: int):
        self._fit = None
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, percent / 100))
        self._apply_zoom()

    def _apply_zoom(self):
        self.zoom_button.setText(f"{int(self._scale * 100)}%")
        if self._document is None:
            return
        if self._continuous:
            # Antes, reconstruir a rolagem contínua voltava para a página 1.
            anchor = self._scroll_anchor()
            self._rebuild_canvas()
            self._scroll_to_page(*anchor)
        else:
            self._show_single_page(self._current_page)

    def _zoom_in(self):
        self._fit = None
        self._scale = min(_MAX_SCALE, self._scale + _ZOOM_STEP)
        self._apply_zoom()

    def _zoom_out(self):
        self._fit = None
        self._scale = max(_MIN_SCALE, self._scale - _ZOOM_STEP)
        self._apply_zoom()

    def _fit_width(self):
        if self._document is None:
            return
        width_pt = self._row_size(self._current_page)[0]
        if width_pt <= 0:
            return
        self._fit = "width"
        self._set_fit_scale((self.scroll_area.viewport().width() - 24) / width_pt)

    def _row_size(self, page: int) -> tuple[float, float]:
        """Largura e altura, em pontos, do que o zoom precisa caber: a página, ou a linha na
        página dupla (página sozinha ocupa o lugar de duas, como nas outras linhas)."""
        geometries = [self._geometry(index) for index in self._row_of(page)]
        if not self._spread:
            return geometries[0].width, geometries[0].height
        gap = _PAGE_GAP / 2 / self._scale  # o vão entre as páginas não cresce com o zoom
        return 2 * max(g.width for g in geometries) + gap, max(g.height for g in geometries)

    def start_presentation(self):
        """Exibir > Apresentação: o documento de trabalho em tela cheia, a partir da página
        atual, na tela em que a janela está. Ao sair, o visualizador vai à última mostrada."""
        path = self.session.path()
        if self._document is None or not path:
            return None
        window = PresentationWindow(path, self._current_page)
        window.finished.connect(self._go_to_page)
        screen = self.screen()
        if screen is not None:
            window.setGeometry(screen.geometry())
        window.showFullScreen()
        window.activateWindow()
        self._presentation = window  # referência Python enquanto a janela existe
        return window

    def page_layout(self) -> str:
        if not self._continuous:
            return SINGLE
        return self._spread or CONTINUOUS

    def set_layout(self, layout: str):
        """Página única, rolagem contínua, página dupla ou livro (capa sozinha)."""
        if layout not in LAYOUTS:
            raise ValueError(f"Layout inválido: {layout}")
        continuous, spread = layout != SINGLE, layout if layout in (DOUBLE, BOOK) else None
        if hasattr(self, "_mode_actions"):
            self._mode_actions[layout].setChecked(True)
            self.mode_button.setIcon(self._mode_actions[layout].icon())
        if (continuous, spread) == (self._continuous, self._spread):
            return
        page = self._current_page
        self._continuous, self._spread = continuous, spread
        if self._document is not None:
            self._rebuild_canvas()
            if continuous:
                self._scroll_to_page(page)  # continua na página em que o usuário estava
            self._refit()
        self.layout_changed.emit(layout)

    def _toggle_thumbnails(self, checked: bool):
        self._show_thumbnails = checked
        self.side_panel.setVisible(checked and self._document is not None)

    def show_side_panel(self, visible: bool) -> None:
        """Mostra ou esconde o painel de miniaturas, marcadores e anexos (e lembra a escolha)."""
        self.thumbnails_button.setChecked(visible)
        self._toggle_thumbnails(visible)

    def _on_thumbnail_selected(self, index: int):
        if index != self._current_page:  # a lista também avisa ao ganhar o foco ou se esvaziar
            self._jump_to_page(index)

    # -- busca de texto ---------------------------------------------------

    def _toggle_search(self):
        if self._document is None:
            return
        if self.search_bar.isVisible():
            self._close_search()
        else:
            # Com um trecho curto selecionado, é ele que se quer procurar.
            selection = self._text_selection
            if selection is not None and selection[0] == selection[2]:
                text = self.selected_text().strip()
                if text and "\n" not in text and "\r" not in text:
                    self.search_bar.set_query(text)
            self.search_bar.show()
            self.search_bar.focus_query()

    def _step_search(self, direction: int):
        """F3 e Shift+F3: a próxima e a anterior; sem busca feita, abre a barra para digitar."""
        if self._matches:
            self._step_match(direction)
        elif self._document is not None:
            self.search_bar.show()
            self.search_bar.focus_query()

    def _close_search(self):
        self._stop_search()
        self.search_bar.hide()
        self.search_bar.clear_count()
        self._matches = []
        self._current_match = -1
        self._refresh_current_render()

    def _search_document(self, query: str):
        """Começa a busca; as páginas são percorridas aos poucos (`_continue_search`), e a
        primeira ocorrência aparece assim que é encontrada, sem esperar o documento todo."""
        if self._document is None or self._search is None:
            return
        self._stop_search()
        self._matches = []
        self._current_match = -1
        if not query.strip():
            self.search_bar.clear_count()
            self._refresh_current_render()
            return
        self._remember_view()  # Voltar traz de volta da ocorrência para onde se estava
        self._search_pages = self._search.iter_pages(query, self.search_bar.match_case(), self.search_bar.whole_word())
        self.search_bar.set_count(0, 0, searching=True)
        self._search_timer.start()

    def _continue_search(self):
        if self._search_pages is None:
            self._search_timer.stop()
            return
        deadline = time.monotonic() + _SEARCH_SLICE_SECONDS
        finished = False
        while time.monotonic() < deadline:
            try:
                page_matches = next(self._search_pages)
            except StopIteration:
                finished = True
                break
            if not page_matches:
                continue
            first_found = not self._matches
            self._matches.extend(page_matches)
            if first_found:
                self._current_match = 0
                self._jump_to_match(0)
        if finished:
            self._stop_search()
        current = self._current_match + 1 if self._matches else 0
        self.search_bar.set_count(current, len(self._matches), searching=not finished)

    def _stop_search(self):
        self._search_timer.stop()
        self._search_pages = None

    def is_searching(self) -> bool:
        return self._search_pages is not None

    def _step_match(self, direction: int):
        if not self._matches:
            return
        self._current_match = (self._current_match + direction) % len(self._matches)
        self.search_bar.set_count(self._current_match + 1, len(self._matches), searching=self.is_searching())
        self._jump_to_match(self._current_match)

    def _jump_to_match(self, match_index: int):
        """Vai até a ocorrência — a posição dela na página, não só a página."""
        match = self._matches[match_index]
        if self._continuous:
            self._scroll_to_page(match.page_index)
            self._render_page_into_label(match.page_index, self._page_labels[match.page_index])
        else:
            self._show_single_page(match.page_index)
        self._refresh_current_render()
        rect = self._user_rect_to_screen(match.page_index, (match.left, match.bottom, match.right, match.top))
        label = self._page_labels[match.page_index if self._continuous else 0]
        offset = label.pixmap_offset() if isinstance(label, PageCanvas) else QPointF(0, 0)
        center = label.mapTo(self.scroll_area.widget(), (rect.center() + offset).toPoint())
        self.scroll_area.ensureVisible(center.x(), center.y(), 60, 80)

    def _refresh_current_render(self):
        if self._document is None:
            return
        if self._continuous:
            for index in list(self._rendered_pages):
                self._render_page_into_label(index, self._page_labels[index])
        else:
            self._show_single_page(self._current_page)

    # -- anotações e marcação -------------------------------------------------

    def _on_markup_state_changed(self):
        tool = self.annotation_state.active_tool()
        drawing_active = (
            (self.annotation_state.is_page_active() and tool in _DRAWING_TOOLS)
            or self.redaction_state.is_page_active()
            or self.measure_state.is_page_active()
            or self.area_pick_state.is_page_active()
        )
        if drawing_active and self._continuous:
            self.set_layout(SINGLE)
        self._update_canvas_cursor()

    def _update_canvas_cursor(self):
        cursor = self._canvas_cursor()
        for canvas in self._page_labels:
            if isinstance(canvas, PageCanvas):
                canvas.setCursor(cursor)

    def _canvas_cursor(self) -> Qt.CursorShape:
        if self.measure_state.is_page_active():
            return Qt.CursorShape.CrossCursor
        if self.redaction_state.is_page_active() or self.area_pick_state.is_page_active():
            return Qt.CursorShape.CrossCursor
        if not self.annotation_state.is_page_active() or self.annotation_state.active_tool() is None:
            # Arrastar move a página ou seleciona texto.
            return Qt.CursorShape.OpenHandCursor if self._hand_mode else Qt.CursorShape.IBeamCursor
        tool = self.annotation_state.active_tool()
        if tool in _DRAWING_TOOLS:
            return Qt.CursorShape.CrossCursor
        if tool == "select":
            return Qt.CursorShape.PointingHandCursor
        return Qt.CursorShape.ArrowCursor

    def _widget_point_to_pdf(self, page_index: int, x: float, y: float) -> tuple[float, float]:
        return self._geometry(page_index).screen_to_user(x, y, self._scale)

    def _on_redaction_selection_changed(self):
        """Mostra a página da área de redação escolhida na lista do painel."""
        selected = self.redaction_state.selected()
        self._show_selection_page(selected.page_index if selected is not None else None)

    def _on_comment_selection_changed(self):
        """Mostra a página do comentário escolhido na lista da aba Anotações."""
        selected = self.annotation_state.selected_comment()
        self._show_selection_page(selected[0] if selected is not None else None)

    def _show_selection_page(self, page_index: int | None):
        if self._document is None or page_index is None or not (0 <= page_index < self._page_count()):
            self._refresh_current_render()
            return
        if self._continuous:
            self._scroll_to_page(page_index)
            self._refresh_current_render()
        elif page_index != self._current_page:
            self._show_single_page(page_index)
        else:
            self._refresh_current_render()

    def _on_canvas_pressed(self, x: float, y: float):
        if self.measure_state.is_page_active():
            self._measure_drag_start_pdf = self._widget_point_to_pdf(self._current_page, x, y)
            self._measure_preview_base = QPixmap(self._page_labels[0].pixmap())
            return
        if self.redaction_state.is_page_active():
            self._redaction_drag_start_pdf = self._widget_point_to_pdf(self._current_page, x, y)
            return
        if self.area_pick_state.is_page_active():
            self._area_drag_start_pdf = self._widget_point_to_pdf(self._current_page, x, y)
            self._area_preview_base = QPixmap(self._page_labels[0].pixmap())
            return
        if self._text_selection_enabled():
            self._start_reading_press(self._page_labels[0], self._current_page, x, y)
            return
        tool = self.annotation_state.active_tool()
        if self._document is None or tool is None:
            return
        page_index = self._current_page
        pdf_point = self._widget_point_to_pdf(page_index, x, y)

        if tool == "select":
            if not self._start_comment_drag(page_index, QPointF(x, y)):
                self._erase_pending_at(page_index, pdf_point)
            return
        if tool in _SHAPE_TOOLS:
            self._shape_start_pdf = pdf_point
            self._shape_preview_base = QPixmap(self._page_labels[0].pixmap())
            return
        if tool == "ink":
            self._ink_points_pdf = [pdf_point]
            # Congela o pixmap já renderizado (sem o traço em progresso) como base do
            # preview: cada movimento do mouse só repinta por cima dessa cópia, em vez de
            # re-renderizar a página inteira via pdfium a cada evento.
            self._ink_preview_base = QPixmap(self._page_labels[0].pixmap())
            return
        if tool in ("highlight", "underline", "strikeout", "stamp"):
            self._drag_start_pdf = pdf_point
            self._drag_preview_base = QPixmap(self._page_labels[0].pixmap())
            if tool == "stamp":  # o carimbo aparece já no clique; arrastar muda o tamanho
                self._show_drag_preview(self._stamp_spec(pdf_point))
            return
        if tool == "note":
            self._prompt_note(page_index, pdf_point)
            return

    def _on_canvas_moved(self, x: float, y: float):
        if self._area_drag_start_pdf is not None and self._area_preview_base is not None:
            # A área acompanha o mouse, já com o conteúdo no tamanho em que vai ficar.
            preview = QPixmap(self._area_preview_base)
            painter = QPainter(preview)
            rect = self._drag_rect(self._area_drag_start_pdf, self._widget_point_to_pdf(self._current_page, x, y))
            self._paint_picked_area(painter, self._current_page, rect, None, QColor("#2f80ed"))
            painter.end()
            self._page_labels[0].setPixmap(preview)
            return
        if self._selection_start_pdf is not None:
            self._extend_selection(self._page_labels[0], x, y)
            return
        if self.measure_state.is_page_active() and self._measure_drag_start_pdf is not None:
            if self._measure_preview_base is None:
                return
            page_index = self._current_page
            end_pdf = self._widget_point_to_pdf(page_index, x, y)
            preview = QPixmap(self._measure_preview_base)
            painter = QPainter(preview)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_measure_segment(painter, page_index, self._measure_drag_start_pdf, end_pdf)
            painter.end()
            self._page_labels[0].setPixmap(preview)
            return

        if self._comment_drag is not None and self._comment_preview_base is not None:
            mode, start, original = self._comment_drag
            delta = QPointF(x, y) - start
            if mode == "move":
                new_rect = original.translated(delta)
            else:
                new_rect = QRectF(original.topLeft(), original.bottomRight() + delta).normalized()
            self._comment_drag_rect = new_rect
            preview = QPixmap(self._comment_preview_base)
            painter = QPainter(preview)
            painter.setPen(QPen(theme.color("accent"), 2, Qt.PenStyle.DashLine))  # como o anel da escolhida
            painter.drawRect(new_rect)
            painter.end()
            self._page_labels[0].setPixmap(preview)
            return
        if self._shape_start_pdf is not None and self._shape_preview_base is not None:
            preview = QPixmap(self._shape_preview_base)
            painter = QPainter(preview)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            spec = self._shape_spec(self._widget_point_to_pdf(self._current_page, x, y))
            self._paint_shape(painter, self._current_page, spec, QColor(f"#{spec.color}"))
            painter.end()
            self._page_labels[0].setPixmap(preview)
            return
        if self._drag_start_pdf is not None and self._drag_preview_base is not None:
            end_pdf = self._widget_point_to_pdf(self._current_page, x, y)
            if self.annotation_state.active_tool() == "stamp":
                self._show_drag_preview(self._stamp_spec(end_pdf))
            else:
                self._show_drag_preview(self._markup_spec(self._drag_start_pdf, end_pdf))
            return
        if self.annotation_state.active_tool() != "ink" or not self._ink_points_pdf:
            return
        page_index = self._current_page
        self._ink_points_pdf.append(self._widget_point_to_pdf(page_index, x, y))
        if self._ink_preview_base is None:
            return
        preview = QPixmap(self._ink_preview_base)
        painter = QPainter(preview)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(f"#{self.annotation_state.active_color()}")
        self._paint_ink_stroke(painter, page_index, self._ink_points_pdf, color, self.annotation_state.width())
        painter.end()
        self._page_labels[0].setPixmap(preview)

    def _on_canvas_released(self, x: float, y: float):
        if self._selection_start_pdf is not None:
            self._finish_selection(self._page_labels[0], self._current_page, x, y)
            return
        if self.measure_state.is_page_active():
            if self._measure_drag_start_pdf is not None:
                page_index = self._current_page
                end_pdf = self._widget_point_to_pdf(page_index, x, y)
                self.measure_state.set_result(page_index, self._measure_drag_start_pdf, end_pdf)
                self._measure_drag_start_pdf = None
                self._measure_preview_base = None
            return

        if self.redaction_state.is_page_active():
            if self._redaction_drag_start_pdf is not None:
                page_index = self._current_page
                end_pdf = self._widget_point_to_pdf(page_index, x, y)
                self._finish_redaction_drag(page_index, self._redaction_drag_start_pdf, end_pdf)
                self._redaction_drag_start_pdf = None
            return

        if self.area_pick_state.is_page_active():
            if self._area_drag_start_pdf is not None:
                end_pdf = self._widget_point_to_pdf(self._current_page, x, y)
                left, bottom, right, top = self._drag_rect(self._area_drag_start_pdf, end_pdf)
                self._area_drag_start_pdf = None
                self._area_preview_base = None
                if right - left >= 2 and top - bottom >= 2:
                    self.area_pick_state.pick(self._current_page, (left, bottom, right, top))
                self._refresh_current_render()  # tira a prévia do arrasto
            return

        tool = self.annotation_state.active_tool()
        page_index = self._current_page
        pdf_point = self._widget_point_to_pdf(page_index, x, y)

        if self._comment_drag is not None:
            self._finish_comment_drag(page_index)
            return
        if self._shape_start_pdf is not None:
            spec = self._shape_spec(pdf_point)
            self._shape_start_pdf = None
            self._shape_preview_base = None
            (x0, y0), (x1, y1) = spec.points
            if max(abs(x1 - x0), abs(y1 - y0)) >= 3:  # um clique sem arrastar não desenha nada
                self.annotation_state.add_pending(spec)
            else:
                self._refresh_current_render()
            return

        if tool == "ink":
            if len(self._ink_points_pdf) >= 2:
                self.annotation_state.add_pending(
                    AnnotationSpec(
                        page_index=page_index,
                        kind="ink",
                        color=self.annotation_state.active_color(),
                        points=list(self._ink_points_pdf),
                        width=self.annotation_state.width(),
                    )
                )
            self._ink_points_pdf = []
            self._ink_preview_base = None
            return

        if self._drag_start_pdf is not None:
            marked = self._stamp_spec(pdf_point) if tool == "stamp" else self._markup_spec(self._drag_start_pdf, pdf_point)
            self._drag_start_pdf = None
            self._drag_preview_base = None
            if marked is not None:
                self.annotation_state.add_pending(marked)
            else:
                self._refresh_current_render()  # tira a prévia

    def _show_drag_preview(self, spec: AnnotationSpec | None) -> None:
        """A página como estava no clique, com a marcação do arrasto por cima."""
        assert self._drag_preview_base is not None
        preview = QPixmap(self._drag_preview_base)
        if spec is not None:
            painter = QPainter(preview)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_pending_spec(painter, self._current_page, spec)
            painter.end()
        self._page_labels[0].setPixmap(preview)

    def _stamp_spec(self, end_pdf) -> AnnotationSpec:
        """O carimbo do clique em `_drag_start_pdf`: no tamanho padrão, ou do tamanho do
        arrasto até `end_pdf`, sem distorcer."""
        assert self._drag_start_pdf is not None
        rotation = self._page_geometry(self._current_page).rotation
        (x0, y0), (x1, y1) = self._drag_start_pdf, end_pdf
        if max(abs(x1 - x0), abs(y1 - y0)) < 3:  # um clique sem arrastar: tamanho padrão
            position, scale = self._drag_start_pdf, 1.0
        else:
            position, scale = stamp_box(self._drag_start_pdf, end_pdf, rotation)
        return AnnotationSpec(
            page_index=self._current_page,
            kind="stamp",
            color=self.annotation_state.active_color(),
            position=position,
            text=self.annotation_state.stamp_text(),
            rotation=rotation,
            scale=scale,
        )

    def _shape_spec(self, end_pdf) -> AnnotationSpec:
        assert self._shape_start_pdf is not None
        return AnnotationSpec(
            page_index=self._current_page,
            kind=self.annotation_state.active_tool() or "square",
            color=self.annotation_state.active_color(),
            points=[self._shape_start_pdf, end_pdf],
            width=self.annotation_state.width(),
        )

    def _start_comment_drag(self, page_index: int, point: QPointF) -> bool:
        """Começa a mover (dentro) ou redimensionar (no canto inferior direito) o comentário
        escolhido na lista, se o clique caiu nele."""
        selected = self.annotation_state.selected_comment()
        if selected is None or selected[0] != page_index:
            return False
        rect = self._user_rect_to_screen(page_index, selected[1])
        corner = rect.bottomRight()
        near_corner = abs(point.x() - corner.x()) <= _RESIZE_HANDLE and abs(point.y() - corner.y()) <= _RESIZE_HANDLE
        if not (near_corner or rect.contains(point)):
            return False
        self._comment_drag = ("resize" if near_corner else "move", point, rect)
        self._comment_drag_rect = None
        self._comment_preview_base = QPixmap(self._page_labels[0].pixmap())
        return True

    def _finish_comment_drag(self, page_index: int) -> None:
        new_rect = self._comment_drag_rect
        self._comment_drag = None
        self._comment_drag_rect = None
        self._comment_preview_base = None
        if new_rect is None:  # clicou sem arrastar
            self._refresh_current_render()
            return
        x0, y0 = self._widget_point_to_pdf(page_index, new_rect.left(), new_rect.top())
        x1, y1 = self._widget_point_to_pdf(page_index, new_rect.right(), new_rect.bottom())
        self._refresh_current_render()
        self.annotation_state.request_comment_geometry(page_index, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))

    # -- seleção de texto (M11) ---------------------------------------------------

    def _text_selection_enabled(self) -> bool:
        """Sem ferramenta de marcação ativa, arrastar na página seleciona texto."""
        return self._links_enabled()

    def _on_canvas_double_clicked(self, x: float, y: float):
        self._on_canvas_clicked_again(x, y, word_range)

    def _on_canvas_triple_clicked(self, x: float, y: float):
        self._on_canvas_clicked_again(x, y, line_range)

    def _on_canvas_clicked_again(self, x: float, y: float, text_range):
        if self._text_selection_enabled():
            self._select_around(self._current_page, x, y, text_range)
        else:
            self._on_canvas_pressed(x, y)  # para uma ferramenta, é só mais um clique

    def _on_scroll_page_pressed(self, canvas: PageCanvas, page_index: int, x: float, y: float):
        if self._text_selection_enabled():
            self._start_reading_press(canvas, page_index, x, y)

    def _on_scroll_page_clicked_again(self, page_index: int, x: float, y: float, text_range):
        if self._text_selection_enabled():
            self._select_around(page_index, x, y, text_range)

    def _start_reading_press(self, canvas: QLabel, page_index: int, x: float, y: float):
        point = self._widget_point_to_pdf(page_index, x, y)
        widget = self._form_widget_at(page_index, point)
        if widget is not None:
            self._edit_form_widget(widget)
            return
        shift = isinstance(canvas, PageCanvas) and canvas.pressed_modifiers & Qt.KeyboardModifier.ShiftModifier
        if shift and not self._hand_mode and self._text_selection is not None and self._selection_anchor is not None:
            # Shift + clique: a seleção vai do começo dela até aqui, mesmo em outra página.
            self._selection_start_pdf = point
            self._selection_press = QPointF(x, y)
            self._update_text_selection(page_index, point)
            return
        self._clear_text_selection()
        # Arrastar a partir de um link seleciona o texto; só o clique o segue.
        self._press_link(canvas, page_index, x, y)
        self._selection_start_pdf = point
        self._selection_start_page = page_index
        self._selection_press = QPointF(x, y)
        self._selection_anchor = None
        if self._hand_mode:
            self._pan_from = canvas.mapToGlobal(QPointF(x, y) + self._canvas_offset(canvas))
            self._pan_travel = 0.0

    # -- links -----------------------------------------------------------------

    def _links_enabled(self) -> bool:
        """Sem ferramenta ativa: com uma, o clique é dela (marcar, medir, redigir)."""
        if self._document is None:
            return False
        if self.measure_state.is_page_active() or self.redaction_state.is_page_active():
            return False
        if self.area_pick_state.is_page_active():
            return False
        return not self.annotation_state.is_page_active() or self.annotation_state.active_tool() is None

    def _page_links(self, page_index: int) -> list[PageLink]:
        links = self._links.get(page_index)
        if links is None:
            try:
                with PDFIUM_LOCK:
                    assert self._document is not None
                    page = self._document[page_index]
                    try:
                        links = page_links(self._document, page, self.session.path(), page_index)
                    finally:
                        page.close()
            except Exception:
                links = []  # um link malformado não impede de ver a página
            self._links[page_index] = links
        return links

    def _link_at(self, page_index: int, x: float, y: float) -> PageLink | None:
        if not self._links_enabled() or not 0 <= page_index < self._page_count():
            return None
        point = self._widget_point_to_pdf(page_index, x, y)
        return next((link for link in self._page_links(page_index) if link.contains(*point)), None)

    def _page_notes(self, page_index: int) -> list[PageNote]:
        notes = self._notes.get(page_index)
        if notes is None:
            try:
                with PDFIUM_LOCK:
                    assert self._document is not None
                    page = self._document[page_index]
                    try:
                        notes = page_notes(page)
                    finally:
                        page.close()
            except Exception:
                notes = []  # um comentário malformado não impede de ver a página
            self._notes[page_index] = notes
        return notes

    def _hover_at(self, page_index: int, x: float, y: float) -> PageLink | PageNote | FormWidget | None:
        link = self._link_at(page_index, x, y)
        if link is not None or not self._links_enabled() or not 0 <= page_index < self._page_count():
            return link
        point = self._widget_point_to_pdf(page_index, x, y)
        widget = self._form_widget_at(page_index, point)
        if widget is not None:
            return widget
        return next((note for note in self._page_notes(page_index) if note.contains(*point)), None)

    def _on_page_hovered(self, canvas: PageCanvas, page_index: int, x: float, y: float):
        """Com o mouse em cima: a mãozinha e o destino do link, a mãozinha num campo para clicar
        e o texto de um comentário."""
        target = self._hover_at(page_index, x, y)
        if target == self._hover_target:
            return
        self._hover_target = target
        clickable = isinstance(target, PageLink) or (isinstance(target, FormWidget) and target.field_type != "text")
        canvas.setCursor(Qt.CursorShape.PointingHandCursor if clickable else self._canvas_cursor())
        tip = ""
        if isinstance(target, PageLink):
            tip = html.escape(self._link_tip(target))
        elif isinstance(target, PageNote):
            tip = self._note_tip(target)
        if not tip:
            QToolTip.hideText()
            return
        position = canvas.mapToGlobal((QPointF(x, y) + canvas.pixmap_offset()).toPoint())
        # Sempre como HTML e com o texto escapado: o que vem do PDF não vira marcação.
        QToolTip.showText(position, f"<span>{tip}</span>", canvas)

    def _note_tip(self, note: PageNote) -> str:
        content = html.escape(note.content.strip()).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
        return f"<b>{html.escape(note.author)}</b><br>{content}" if note.author else content

    def _link_tip(self, link: PageLink) -> str:
        if link.named:
            return tr(_NAMED_LINK_TIPS[link.named])
        if link.file:
            return tr("Abrir {file}").format(file=link.file)
        if link.target_page is not None:
            return tr("Ir para a página {page}").format(page=link.target_page + 1)
        if link.url.lower().startswith("mailto:"):
            return tr("Escrever para {address}").format(address=link.url[len("mailto:") :].split("?")[0])
        return link.url

    def _press_link(self, canvas: QLabel, page_index: int, x: float, y: float):
        left = isinstance(canvas, PageCanvas) and canvas.pressed_button == Qt.MouseButton.LeftButton
        link = self._link_at(page_index, x, y) if left else None
        self._link_press = (page_index, link, QPointF(x, y)) if link is not None else None

    def _release_link(self, page_index: int, x: float, y: float):
        """Segue o link se o botão soltou nele, sem ter arrastado (arrasto seleciona texto)."""
        press, self._link_press = self._link_press, None
        if press is None or press[0] != page_index:
            return
        _page, link, start = press
        if (QPointF(x, y) - start).manhattanLength() > _LINK_CLICK_SLOP:
            return
        if not link.contains(*self._widget_point_to_pdf(page_index, x, y)):
            return
        self._clear_text_selection()
        self._follow_link(link)

    def _follow_link(self, link: PageLink):
        if link.url:
            self._open_url(link.url)
        elif link.named:
            {
                "NextPage": self._go_next,
                "PrevPage": self._go_prev,
                "FirstPage": self._go_first,
                "LastPage": self._go_last,
                "GoBack": self.go_back,
                "GoForward": self.go_forward,
            }[link.named]()
        elif link.file:
            self._open_linked_file(link)
        elif link.target_page is not None:
            self._jump_to_destination(link.target_page, link.target_top)

    def _open_linked_file(self, link: PageLink):
        """Outro PDF abre no próprio app, a partir da pasta do arquivo do usuário (o documento
        de trabalho pode estar numa pasta temporária), já no destino que o link pede."""
        source = self.session.source_path()
        path = linked_pdf_path(link.file, str(Path(source).parent)) if source else ""
        if not path:
            message = html.escape(tr("Arquivo não encontrado: {file}").format(file=link.file))
            QToolTip.showText(QCursor.pos(), message, self)
            return
        opened = self.open_path(path)  # a janela devolve a aba; sem ela, é este visualizador
        viewer = getattr(opened, "viewer", self if opened is True else None)
        target = file_destination(path, link)
        if viewer is not None and target is not None:
            viewer._jump_to_destination(*target)

    def _open_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))  # no navegador ou no programa de e-mail

    # -- seleção de texto ---------------------------------------------------------

    def _extend_selection(self, canvas: QLabel, x: float, y: float):
        """O arrasto em andamento: a seleção vai até o caractere sob o mouse, que na rolagem pode
        estar em outra página, e a tela acompanha quando o mouse chega à borda."""
        if self._selection_start_pdf is None or self._selection_press is None:
            return
        point = QPointF(x, y) + self._canvas_offset(canvas)
        if self._hand_mode:
            # A página anda junto com o mouse: a distância que conta é a da tela. Arrastada, um
            # link sob o mouse não é mais um clique.
            self._pan_to(canvas.mapToGlobal(point))
            if self._pan_travel > _LINK_CLICK_SLOP:
                self._link_press = None
            return
        if self._text_selection is None and (QPointF(x, y) - self._selection_press).manhattanLength() <= _LINK_CLICK_SLOP:
            return
        page, page_x, page_y = self._page_at(canvas.mapToGlobal(point))
        self._update_text_selection(page, self._widget_point_to_pdf(page, page_x, page_y))
        inside = canvas.mapTo(self.scroll_area.widget(), point.toPoint())
        self.scroll_area.ensureVisible(inside.x(), inside.y(), 0, 24)

    def _canvas_offset(self, canvas: QLabel) -> QPointF:
        return canvas.pixmap_offset() if isinstance(canvas, PageCanvas) else QPointF(0, 0)

    def _finish_selection(self, canvas: QLabel, page_index: int, x: float, y: float):
        if self._selection_start_pdf is None:
            return
        if self._hand_mode:
            self._pan_from = None  # o último movimento já levou a página até aqui
        else:
            self._extend_selection(canvas, x, y)
        self._selection_start_pdf = None
        self._selection_press = None
        self._release_link(page_index, x, y)

    def _char_on_page(self, page_index: int, point, exact: bool = False) -> int | None:
        x, y = point
        with PDFIUM_LOCK:
            assert self._document is not None
            page = self._document[page_index]
            textpage = page.get_textpage()
            try:
                return char_at(textpage, x, y, exact=exact)
            finally:
                textpage.close()
                page.close()

    def _update_text_selection(self, end_page: int, end_pdf):
        if self._selection_anchor is None:
            self._selection_anchor = self._char_on_page(self._selection_start_page, self._selection_start_pdf)
        end_char = self._char_on_page(end_page, end_pdf)
        if self._selection_anchor is None or end_char is None:
            return  # numa página sem texto (escaneada) a seleção fica como estava
        first, last = sorted(((self._selection_start_page, self._selection_anchor), (end_page, end_char)))
        self._set_text_selection((*first, *last))

    def _select_around(self, page_index: int, x: float, y: float, text_range):
        """Duplo clique, a palavra; triplo clique, a linha."""
        point = self._widget_point_to_pdf(page_index, x, y)
        widget = self._form_widget_at(page_index, point)
        if widget is not None:
            self._edit_form_widget(widget)
            return
        if self._hand_mode:
            return
        index = self._char_on_page(page_index, point, exact=True)
        if index is None:
            return
        with PDFIUM_LOCK:
            assert self._document is not None
            page = self._document[page_index]
            textpage = page.get_textpage()
            try:
                start, count = text_range(textpage, index)
            finally:
                textpage.close()
                page.close()
        self._selection_start_page, self._selection_anchor = page_index, start
        self._set_text_selection((page_index, start, page_index, start + count - 1))

    def select_all_text(self):
        """Ctrl+A: o documento inteiro, como nos leitores de PDF."""
        if self._document is not None and self._page_count():
            self._selection_start_page, self._selection_anchor = 0, 0
            self._set_text_selection((0, 0, self._page_count() - 1, -1))

    def _set_text_selection(self, selection: tuple[int, int, int, int] | None):
        self._text_selection, self._selection_rects = selection, {}
        if self._continuous:
            for index in self._rendered_pages:
                self._apply_selection(index, self._page_labels[index])
        elif self._page_labels:
            self._apply_selection(self._current_page, self._page_labels[0])

    def _clear_text_selection(self):
        if self._text_selection is not None:
            self._set_text_selection(None)

    def _selection_span(self, page_index: int, textpage) -> tuple[int, int] | None:
        """(início, quantidade) da seleção em uma página aberta, ou None se não passa por ela."""
        if self._text_selection is None:
            return None
        first_page, first_char, last_page, last_char = self._text_selection
        total = textpage.count_chars()
        if not first_page <= page_index <= last_page or not total:
            return None
        start = first_char if page_index == first_page else 0
        end = last_char if page_index == last_page and last_char >= 0 else total - 1
        return (start, end - start + 1) if end >= start else None

    def _apply_selection(self, page_index: int, label: QLabel):
        if not isinstance(label, PageCanvas):
            return
        rects = self._selection_rects.get(page_index)
        if rects is None:
            rects = []
            if self._text_selection is not None and self._document is not None:
                with PDFIUM_LOCK:
                    page = self._document[page_index]
                    textpage = page.get_textpage()
                    try:
                        span = self._selection_span(page_index, textpage)
                        if span is not None:
                            rects = [textpage.get_rect(i) for i in range(textpage.count_rects(*span))]
                    finally:
                        textpage.close()
                        page.close()
            self._selection_rects[page_index] = rects
        screen = [self._user_rect_to_screen(page_index, rect).normalized() for rect in rects]
        label.set_selection(screen, _TEXT_SELECTION_COLOR)

    def selected_text(self) -> str:
        if self._text_selection is None or self._document is None:
            return ""
        parts = []
        for page_index in range(self._text_selection[0], self._text_selection[2] + 1):
            with PDFIUM_LOCK:
                page = self._document[page_index]
                textpage = page.get_textpage()
                try:
                    span = self._selection_span(page_index, textpage)
                    if span is not None:
                        parts.append(textpage.get_text_range(*span))
                finally:
                    textpage.close()
                    page.close()
        return "\n".join(parts)

    def _copy_allowed(self) -> bool:
        if self._document is None:
            return True
        with PDFIUM_LOCK:
            return can_copy_text(self._document)

    def copy_selected_text(self):
        if not self._copy_allowed():
            if self._text_selection is not None:
                QToolTip.showText(QCursor.pos(), tr("O autor deste PDF bloqueou a cópia de texto."), self)
            return
        text = self.selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def _markup_spec(self, start_pdf, end_pdf) -> AnnotationSpec | None:
        """Realce, sublinhado ou riscado do texto entre os dois pontos (None se não pegou texto)."""
        with PDFIUM_LOCK:
            quads = self._text_quads(self._current_page, start_pdf, end_pdf)
        if not quads:
            return None
        return AnnotationSpec(
            page_index=self._current_page,
            kind=self.annotation_state.active_tool() or "highlight",
            color=self.annotation_state.active_color(),
            quads=quads,
        )

    def _text_quads(self, page_index: int, start_pdf, end_pdf) -> list:
        """Retângulos do texto entre os dois pontos (chamar com `PDFIUM_LOCK`)."""
        assert self._document is not None
        page = self._document[page_index]
        textpage = page.get_textpage()
        try:
            start_index = textpage.get_index(start_pdf[0], start_pdf[1], 6, 6)
            end_index = textpage.get_index(end_pdf[0], end_pdf[1], 6, 6)
            if start_index is None or end_index is None:
                return []
            lo, hi = sorted((start_index, end_index))
            count = hi - lo + 1
            n_rects = textpage.count_rects(lo, count)
            return [textpage.get_rect(i) for i in range(n_rects)]
        finally:
            textpage.close()
            page.close()

    def _finish_redaction_drag(self, page_index: int, start_pdf, end_pdf):
        (x1, y1), (x2, y2) = start_pdf, end_pdf
        left, right = sorted((x1, x2))
        bottom, top = sorted((y1, y2))
        if right - left < 2 or top - bottom < 2:
            return
        self.redaction_state.add_pending(
            RedactionRect(page_index=page_index, left=left, bottom=bottom, right=right, top=top)
        )

    def _prompt_note(self, page_index: int, pdf_point):
        text, ok = QInputDialog.getMultiLineText(self, tr("Nota adesiva"), tr("Texto da nota:"))
        if ok and text.strip():
            self.annotation_state.add_pending(
                AnnotationSpec(
                    page_index=page_index,
                    kind="note",
                    color=self.annotation_state.active_color(),
                    position=pdf_point,
                    text=text.strip(),
                    rotation=self._page_geometry(page_index).rotation,
                )
            )

    def _erase_pending_at(self, page_index: int, pdf_point):
        x, y = pdf_point
        for spec in reversed(self.annotation_state.pending()):
            if spec.page_index != page_index:
                continue
            left, bottom, right, top = spec_rect(spec)
            if left <= x <= right and bottom <= y <= top:
                self.annotation_state.remove_pending(spec)
                return

    # -- formulários (A02) ---------------------------------------------------------

    def _load_form_widgets(self, path: str) -> list[FormWidget]:
        try:
            return ListFormWidgets().run(path)
        except Exception:
            return []  # um formulário malformado não impede de ver o PDF

    def _with_form_fields(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        widgets = [w for w in self._form_widgets if w.page_index == page_index and not w.read_only]
        if not widgets:
            return pixmap
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_FORM_FIELD_COLOR)
        for widget in widgets:
            painter.drawRect(self._user_rect_to_screen(page_index, widget.rect))
        painter.end()
        return result

    def _form_widget_at(self, page_index: int, pdf_point) -> FormWidget | None:
        x, y = pdf_point
        for widget in reversed(self._form_widgets):
            left, bottom, right, top = widget.rect
            if widget.page_index == page_index and not widget.read_only and left <= x <= right and bottom <= y <= top:
                return widget
        return None

    def _edit_form_widget(self, widget: FormWidget):
        if widget.field_type == "checkbox":
            checked = widget.value not in ("", "/Off")
            self._fill_form_fields({widget.name: "/Off" if checked else (widget.on_state or "/Yes")})
        elif widget.field_type == "radio":
            if widget.on_state and widget.value != widget.on_state:
                self._fill_form_fields({widget.name: widget.on_state})
        elif widget.field_type in ("dropdown", "listbox"):
            value = self._choose_option(widget)
            if value is not None and value != widget.value:
                self._fill_form_fields({widget.name: value})
        else:
            self._open_field_editor(widget)

    def _field_canvas(self, widget: FormWidget) -> PageCanvas:
        canvas = self._page_labels[widget.page_index if self._continuous else 0]
        assert isinstance(canvas, PageCanvas)
        return canvas

    def _field_screen_rect(self, widget: FormWidget) -> QRectF:
        canvas = self._field_canvas(widget)
        rect = self._user_rect_to_screen(widget.page_index, widget.rect).normalized()
        return rect.translated(canvas.pixmap_offset())

    def _choose_option(self, widget: FormWidget) -> str | None:
        menu = QMenu(self)
        for value, text in widget.options:
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(value == widget.value)
            action.setData(value)
        canvas = self._field_canvas(widget)
        chosen = menu.exec(canvas.mapToGlobal(self._field_screen_rect(widget).bottomLeft().toPoint()))
        return None if chosen is None else chosen.data()

    def _open_field_editor(self, widget: FormWidget):
        canvas = self._field_canvas(widget)
        rect = self._field_screen_rect(widget)
        editor: QLineEdit | QPlainTextEdit
        if widget.multiline:
            editor = QPlainTextEdit(widget.value, canvas)
            editor.installEventFilter(self)  # grava ao perder o foco (`eventFilter`)
        else:
            editor = QLineEdit(widget.value, canvas)
            editor.editingFinished.connect(self._finish_field_edit)
        font = editor.font()
        font.setPixelSize(max(8, int(min(rect.height() * 0.7, 12 * self._scale))))
        editor.setFont(font)
        editor.setGeometry(rect.toAlignedRect())
        self._field_editor = (editor, widget)
        for key, handler in (
            (Qt.Key.Key_Escape, lambda: self._finish_field_edit(commit=False)),
            (Qt.Key.Key_Tab, lambda: self._tab_to_field(1)),
            ("Shift+Tab", lambda: self._tab_to_field(-1)),
        ):
            shortcut = QShortcut(QKeySequence(key), editor)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(handler)
        editor.show()
        editor.setFocus()
        editor.selectAll()
        self.scroll_area.ensureWidgetVisible(editor)

    def _finish_field_edit(self, commit: bool = True) -> bool:
        """Fecha o editor; True se o texto mudou e o documento vai ganhar uma versão nova."""
        if self._field_editor is None:
            return False
        (editor, widget), self._field_editor = self._field_editor, None
        text = editor.toPlainText() if isinstance(editor, QPlainTextEdit) else editor.text()
        editor.hide()  # dispara editingFinished de novo, que já não acha editor aberto
        editor.deleteLater()
        if commit and text != widget.value:
            self._fill_form_fields({widget.name: text})
            return True
        return False

    def _tab_to_field(self, direction: int):
        """Tab e Shift+Tab: grava o campo e abre o próximo de texto (ou o anterior), como nos
        leitores de PDF. Se gravou, o próximo abre quando a versão nova carregar (`_reload`)."""
        if self._field_editor is None:
            return
        current = self._field_editor[1]
        fields = [w for w in self._form_widgets if w.field_type == "text" and not w.read_only]
        if current not in fields:
            return
        self._next_field = fields[(fields.index(current) + direction) % len(fields)].name
        if not self._finish_field_edit():
            self._layout_timer.start()

    def _open_next_field(self):
        name, self._next_field = self._next_field, None
        widget = next((w for w in self._form_widgets if w.name == name), None)
        if widget is not None and self._document is not None:
            if widget.page_index != self._current_page:
                self._go_to_page(widget.page_index)
            self._open_field_editor(widget)

    def _fill_form_fields(self, values: dict[str, str]):
        input_path = self.session.path()
        assert input_path is not None  # há um documento aberto
        output_path = self.session.new_version_path()
        run_task(
            self,
            tr("Preencher formulário"),
            lambda _progress: FillFormFields().run(input_path, output_path, values),
            on_success=lambda _result: self.session.open(output_path),
        )
