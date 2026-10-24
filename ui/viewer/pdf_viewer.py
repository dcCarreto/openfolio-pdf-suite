"""Widget central: visualizador de PDF com miniaturas, zoom, página única/rolagem
contínua, busca de texto e preenchimento de formulários."""

import dataclasses
import time

import pypdfium2 as pdfium
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.annotations import STAMP_FONT_SIZE, AnnotationSpec, arrow_head, spec_rect, stamp_box
from core.base import known_password, remember_password
from core.document_info import document_notices
from core.form_fields import FillFormFields, FormWidget, ListFormWidgets
from core.geometry import PageGeometry
from core.progress import PDFIUM_LOCK
from core.redaction import RedactionRect
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.errors import show_error
from ui.i18n import tr, tr_message
from ui.area_pick_state import AreaPickState
from ui.measure_state import MeasureState, format_distance
from ui.redaction_state import RedactionState
from ui.tasks import run_task
from ui.viewer.page_canvas import PageCanvas
from ui.viewer.presentation import PresentationWindow
from ui.viewer.render import logical_size, render_page
from ui.viewer.search import DocumentSearch, SearchMatch
from ui.viewer.search_bar import SearchBar
from ui.viewer.side_panel import DocumentSidePanel
from ui.viewer.thumbnail_list import ThumbnailList
from ui.viewer.viewer_icons import (
    build_continuous_page_icon,
    build_double_page_icon,
    build_fit_page_icon,
    build_fit_width_icon,
    build_next_page_icon,
    build_open_icon,
    build_prev_page_icon,
    build_rotate_icon,
    build_search_icon,
    build_single_page_icon,
    build_thumbnails_icon,
    build_zoom_in_icon,
    build_zoom_out_icon,
)

_MIN_SCALE = 0.3
_MAX_SCALE = 4.0
_ZOOM_STEP = 0.15
_DEFAULT_SCALE = 1.2
_HIGHLIGHT_COLOR = QColor(255, 235, 59, 110)  # outras ocorrências da busca
_CURRENT_MATCH_COLOR = QColor(255, 152, 0, 150)  # a ocorrência atual
_TEXT_SELECTION_COLOR = QColor(33, 150, 243, 90)
_FORM_FIELD_COLOR = QColor(100, 149, 237, 45)  # campos preenchíveis, como nos leitores de PDF
_DRAWING_TOOLS = ("highlight", "underline", "strikeout", "note", "ink", "square", "circle", "arrow", "stamp")
_SHAPE_TOOLS = ("square", "circle", "arrow")
_RESIZE_HANDLE = 10  # pixels em volta do canto inferior direito que redimensionam
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
# Busca incremental: tempo máximo por fatia antes de devolver o controle à janela.
_SEARCH_SLICE_SECONDS = 0.03


class PdfViewer(QWidget):
    """Mostra o PDF atualmente aberto na sessão compartilhada. A única edição feita aqui é
    preencher os campos de formulário (página única, sem ferramenta ativa): cada campo
    preenchido vira uma versão do documento, que Ctrl+Z desfaz e "Salvar" grava."""

    verify_signatures_requested = Signal()
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
        self._selection_base: QPixmap | None = None
        self._text_selection: tuple[int, int, int] | None = None
        self._selection_rects: list = []
        self._measure_drag_start_pdf: tuple[float, float] | None = None
        self._measure_preview_base: QPixmap | None = None
        self._form_widgets: list[FormWidget] = []
        self._field_editor: tuple[QLineEdit, FormWidget] | None = None
        self._translatable_tooltips: list[tuple[QWidget, str]] = []
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
            (("Ctrl+C",), self.copy_selected_text),
        ):
            for key in keys:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(handler)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.scroll_area.viewport().installEventFilter(self)

        session.path_changed.connect(self._reload)
        annotation_state.tool_changed.connect(self._on_markup_state_changed)
        annotation_state.pending_changed.connect(self._refresh_current_render)
        annotation_state.selection_changed.connect(self._on_comment_selection_changed)
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

        # Aviso sobre o documento aberto (protegido, assinado, com formulário ou camadas).
        self.notice_bar = QWidget()
        self.notice_bar.setObjectName("documentNotice")
        notice_layout = QHBoxLayout(self.notice_bar)
        notice_layout.setContentsMargins(10, 4, 10, 4)
        self.notice_label = QLabel()
        self.notice_label.setWordWrap(True)
        self.verify_button = QPushButton(tr("Verificar"))
        self.verify_button.setToolTip(tr("Verificar as assinaturas na aba Assinatura"))
        self.verify_button.clicked.connect(self.verify_signatures_requested)
        notice_layout.addWidget(self.notice_label, 1)
        notice_layout.addWidget(self.verify_button)
        self.notice_bar.hide()
        layout.addWidget(self.notice_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.thumbnail_list = ThumbnailList()
        self.thumbnail_list.page_selected.connect(self._on_thumbnail_selected)
        self.thumbnail_list.pages_selected.connect(self.session.set_selected_pages)
        self.side_panel = DocumentSidePanel(self.thumbnail_list)
        self.side_panel.page_requested.connect(self._go_to_page)
        self.side_panel.hide()
        body_layout.addWidget(self.side_panel)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_empty_state())

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_pages)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._apply_pending_scroll)
        self.content_stack.addWidget(self.scroll_area)

        body_layout.addWidget(self.content_stack, 1)
        layout.addWidget(body, 1)

        self._set_document_controls_enabled(False)

    def _build_empty_state(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self._empty_label = QLabel(tr("Nenhum PDF aberto"))
        self._empty_label.setObjectName("pageSubtitle")
        self._empty_open_button = QPushButton(tr("Abrir PDF..."))
        self._empty_open_button.clicked.connect(self._browse_open)

        layout.addWidget(self._empty_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._empty_open_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return widget

    def retranslate(self):
        """Troca os textos para o idioma atual sem recarregar o documento nem perder zoom,
        página e modo de exibição."""
        for widget, text in self._translatable_tooltips:
            widget.setToolTip(tr(text))
        self._empty_label.setText(tr("Nenhum PDF aberto"))
        self._empty_open_button.setText(tr("Abrir PDF..."))
        self.search_bar.retranslate()
        self.thumbnail_list.retranslate()
        self.side_panel.retranslate()
        self.verify_button.setText(tr("Verificar"))
        self.verify_button.setToolTip(tr("Verificar as assinaturas na aba Assinatura"))
        if getattr(self, "_notices", None) is not None:
            self.notice_label.setText("  ·  ".join(tr_message(message) for message in self._notices.messages))
        self._update_page_indicator()

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("viewerToolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        open_button = self._tool_button(build_open_icon(), "Abrir PDF...")
        open_button.clicked.connect(self._browse_open)
        layout.addWidget(open_button)
        layout.addSpacing(4)

        prev_button = self._tool_button(build_prev_page_icon(), "Página anterior")
        prev_button.clicked.connect(self._go_prev)
        next_button = self._tool_button(build_next_page_icon(), "Próxima página")
        next_button.clicked.connect(self._go_next)
        # Clicar no indicador (ou Ctrl+G) pede o número da página para ir direto a ela.
        self.page_indicator = QPushButton()
        self.page_indicator.setObjectName("pageIndicatorButton")
        self.page_indicator.setFlat(True)
        self.page_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.page_indicator.setToolTip(tr("Ir para a página... (Ctrl+G)"))
        self._translatable_tooltips.append((self.page_indicator, "Ir para a página... (Ctrl+G)"))
        self.page_indicator.clicked.connect(self._ask_go_to_page)
        layout.addWidget(prev_button)
        layout.addWidget(self.page_indicator)
        layout.addWidget(next_button)
        layout.addSpacing(4)

        zoom_out_button = self._tool_button(build_zoom_out_icon(), "Diminuir zoom")
        zoom_out_button.clicked.connect(self._zoom_out)
        zoom_in_button = self._tool_button(build_zoom_in_icon(), "Aumentar zoom")
        zoom_in_button.clicked.connect(self._zoom_in)
        fit_width_button = self._tool_button(build_fit_width_icon(), "Ajustar à largura")
        fit_width_button.clicked.connect(self._fit_width)
        fit_page_button = self._tool_button(build_fit_page_icon(), "Ajustar à página (Ctrl+0)")
        fit_page_button.clicked.connect(self._fit_page)
        rotate_button = self._tool_button(build_rotate_icon(), "Girar a visualização (o arquivo não muda)")
        rotate_button.clicked.connect(self._rotate_view)
        self._zoom_label = QLabel(f"{int(self._scale * 100)}%")
        layout.addWidget(zoom_out_button)
        layout.addWidget(self._zoom_label)
        layout.addWidget(zoom_in_button)
        layout.addWidget(fit_width_button)
        layout.addWidget(fit_page_button)
        layout.addWidget(rotate_button)
        layout.addSpacing(4)

        self.single_page_button = self._tool_button(build_single_page_icon(), "Página única")
        self.single_page_button.setCheckable(True)
        self.single_page_button.setChecked(True)
        self.single_page_button.clicked.connect(lambda: self.set_layout(SINGLE))

        self.continuous_button = self._tool_button(build_continuous_page_icon(), "Rolagem contínua")
        self.continuous_button.setCheckable(True)
        self.continuous_button.clicked.connect(lambda: self.set_layout(CONTINUOUS))

        self.double_page_button = self._tool_button(build_double_page_icon(), "Página dupla")
        self.double_page_button.setCheckable(True)
        self.double_page_button.clicked.connect(lambda: self.set_layout(DOUBLE))

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.single_page_button)
        self._mode_group.addButton(self.continuous_button)
        self._mode_group.addButton(self.double_page_button)
        layout.addWidget(self.single_page_button)
        layout.addWidget(self.continuous_button)
        layout.addWidget(self.double_page_button)
        layout.addSpacing(4)

        self.thumbnails_button = self._tool_button(build_thumbnails_icon(), "Painel lateral (miniaturas, marcadores, anexos)")
        self.thumbnails_button.setCheckable(True)
        self.thumbnails_button.setChecked(True)
        self.thumbnails_button.clicked.connect(self._toggle_thumbnails)
        layout.addWidget(self.thumbnails_button)

        search_button = self._tool_button(build_search_icon(), "Buscar")
        search_button.clicked.connect(self._toggle_search)
        layout.addWidget(search_button)

        layout.addStretch()

        self._document_dependent_widgets = [
            prev_button,
            next_button,
            zoom_out_button,
            zoom_in_button,
            fit_width_button,
            fit_page_button,
            rotate_button,
            self.page_indicator,
            self.single_page_button,
            self.continuous_button,
            self.double_page_button,
            self.thumbnails_button,
            search_button,
        ]
        return toolbar

    def _tool_button(self, icon, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("viewerToolButton")
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(30, 30)
        button.setToolTip(tr(tooltip))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._translatable_tooltips.append((button, tooltip))
        return button

    def _set_document_controls_enabled(self, enabled: bool):
        for widget in self._document_dependent_widgets:
            widget.setEnabled(enabled)

    # -- carregamento do documento -----------------------------------------

    def _browse_open(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar arquivo"), "", "PDF (*.pdf)")
        if path:
            self.open_path(path)

    def close_document(self):
        """Fecha o documento no pdfium (ao fechar a janela): no Windows, um arquivo aberto
        não pode ser apagado, e as versões temporárias do documento precisam sair."""
        if self._document is not None:
            self.thumbnail_list.clear_document()
            with PDFIUM_LOCK:
                self._document.close()
            self._document = None

    def _reload(self):
        path = self.session.path()
        # Uma versão nova do mesmo documento (operação, desfazer, refazer) mantém a página
        # em que o usuário estava; outro documento começa na primeira.
        keep_page = self._current_page if self.session.last_change() == "version" else 0
        self._finish_field_edit(commit=False)
        self._form_widgets = []
        self._geometries = {}
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

        self._document = document
        self._text_selection, self._selection_rects = None, []
        if self.session.last_change() != "version":
            self._view_rotation = 0  # outro documento começa sem rotação da tela
        self._search = DocumentSearch(self._document)
        self._matches = []
        self._current_match = -1
        self._current_page = min(keep_page, max(self._page_count() - 1, 0))
        if self._continuous and self._current_page:
            self._pending_scroll = (self._current_page, 0.0)
        self.search_bar.hide()
        self.annotation_state.clear_pending()
        self.redaction_state.clear_pending()
        self.measure_state.clear_result()

        self._set_document_controls_enabled(True)
        self.thumbnail_list.load_document(self._document)
        self.side_panel.load(path)
        self.side_panel.setVisible(self._show_thumbnails)
        self._update_notices(path)
        self._form_widgets = self._load_form_widgets(path)
        self.content_stack.setCurrentIndex(1)
        self._rebuild_canvas()

    def _update_notices(self, path: str):
        notices = document_notices(path)
        self._notices = notices
        self.notice_label.setText("  ·  ".join(tr_message(message) for message in notices.messages))
        self.verify_button.setVisible(notices.signature_count > 0)
        self.notice_bar.setVisible(bool(notices.messages))

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
            vlayout.setContentsMargins(margin, margin, margin, margin)
            vlayout.setSpacing(spacing)

            offset = margin
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
            label.mouse_pressed.connect(self._on_canvas_pressed)
            label.mouse_moved.connect(self._on_canvas_moved)
            label.mouse_released.connect(self._on_canvas_released)
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
        label = QLabel()
        label.setFixedSize(max(1, int(width_pt * self._scale)), max(1, int(height_pt * self._scale)))
        label.setStyleSheet("background-color: white;")
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
        pixmap = self._with_text_selection(pixmap, index)
        return self._with_measure_overlay(pixmap, index)

    def _with_text_selection(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        if self._text_selection is None or self._text_selection[0] != page_index or not self._selection_rects:
            return pixmap
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_TEXT_SELECTION_COLOR)
        for rect in self._selection_rects:
            painter.drawRect(self._user_rect_to_screen(page_index, rect))
        painter.end()
        return result

    def _show_single_page(self, index: int):
        if self._document is None or not (0 <= index < self._page_count()):
            return
        if self._text_selection is not None and self._text_selection[0] != index:
            self._text_selection, self._selection_rects = None, []
        self._finish_field_edit()  # o editor fica sobre a página: grava antes de trocá-la
        self._current_page = index
        pixmap = self._render_with_overlays(index)
        self._page_labels[0].setPixmap(pixmap)
        self._page_labels[0].resize(logical_size(pixmap))
        self.thumbnail_list.select_page(index)
        self._update_page_indicator()

    def _render_page_into_label(self, index: int, label: QLabel):
        label.setPixmap(self._render_with_overlays(index))
        self._rendered_pages.add(index)

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
        if comment is not None:
            painter.setPen(QPen(QColor("#ff5252"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._user_rect_to_screen(page_index, comment[1]).adjusted(-3, -3, 3, 3))
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
            self.page_indicator.setText("")
            return
        # Curto na barra ("3 / 12"), completo na dica: a barra precisa caber no visualizador
        # mesmo com a janela em 1280 px.
        text = f"{self._current_page + 1} / {self._page_count()}"
        self.page_indicator.setText(text)
        self.page_indicator.setToolTip(
            tr("Página {current} de {total}").format(current=self._current_page + 1, total=self._page_count())
            + " — " + tr("Ir para a página... (Ctrl+G)")
        )
        self.page_indicator.setFixedWidth(self.page_indicator.fontMetrics().horizontalAdvance(text) + 16)

    # -- navegação e zoom -----------------------------------------------------

    def _go_prev(self):
        if self._spread:
            self._step_row(-1)
        elif self._continuous:
            self._scroll_to_page(max(0, self._current_page - 1))
        else:
            self._show_single_page(max(0, self._current_page - 1))

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

    def _step_row(self, direction: int):
        """Na página dupla, avança ou volta uma linha (duas páginas)."""
        rows = self._rows()
        current = next((n for n, row in enumerate(rows) if self._current_page in row), 0)
        self._scroll_to_page(rows[max(0, min(len(rows) - 1, current + direction))][0])

    def _go_first(self):
        self._go_to_page(0)

    def _go_last(self):
        if self._document is not None:
            self._go_to_page(self._page_count() - 1)

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
            self._go_to_page(number - 1)

    def _fit_page(self):
        """Zoom para a página inteira caber na área visível."""
        if self._document is None:
            return
        width, height = self._row_size(self._current_page)
        if width <= 0 or height <= 0:
            return
        viewport = self.scroll_area.viewport()
        scale = min((viewport.width() - 24) / width, (viewport.height() - 24) / height)
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, scale))
        self._apply_zoom()

    def _rotate_view(self):
        """Gira a página na tela em 90° (para ler um escaneado de lado); o arquivo não muda
        — para girar de verdade, use a aba Páginas."""
        if self._document is None:
            return
        self._view_rotation = (self._view_rotation + 90) % 360
        page = self._current_page
        self._rebuild_canvas()
        self._go_to_page(page)

    def eventFilter(self, watched, event):
        # Ctrl + roda do mouse: zoom (como nos leitores de PDF), em vez de rolar.
        if (
            event.type() == QEvent.Type.Wheel
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self._document is not None
        ):
            if event.angleDelta().y() > 0:
                self._zoom_in()
            elif event.angleDelta().y() < 0:
                self._zoom_out()
            return True
        return super().eventFilter(watched, event)

    def _apply_zoom(self):
        self._zoom_label.setText(f"{int(self._scale * 100)}%")
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
        self._scale = min(_MAX_SCALE, self._scale + _ZOOM_STEP)
        self._apply_zoom()

    def _zoom_out(self):
        self._scale = max(_MIN_SCALE, self._scale - _ZOOM_STEP)
        self._apply_zoom()

    def _fit_width(self):
        if self._document is None:
            return
        width_pt = self._row_size(self._current_page)[0]
        if width_pt <= 0:
            return
        viewport_width = self.scroll_area.viewport().width() - 24
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, viewport_width / width_pt))
        self._apply_zoom()

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
        if hasattr(self, "single_page_button"):
            buttons = {SINGLE: self.single_page_button, CONTINUOUS: self.continuous_button}
            buttons.get(layout, self.double_page_button).setChecked(True)
        if (continuous, spread) == (self._continuous, self._spread):
            return
        page = self._current_page
        self._continuous, self._spread = continuous, spread
        if self._document is not None:
            self._rebuild_canvas()
            if continuous:
                self._scroll_to_page(page)  # continua na página em que o usuário estava
        self.layout_changed.emit(layout)

    def _toggle_thumbnails(self, checked: bool):
        self._show_thumbnails = checked
        self.side_panel.setVisible(checked and self._document is not None)

    def show_side_panel(self, visible: bool) -> None:
        """Mostra ou esconde o painel de miniaturas, marcadores e anexos (e lembra a escolha)."""
        self.thumbnails_button.setChecked(visible)
        self._toggle_thumbnails(visible)

    def _on_thumbnail_selected(self, index: int):
        if self._continuous:
            self._scroll_to_page(index)
        else:
            self._show_single_page(index)

    # -- busca de texto ---------------------------------------------------

    def _toggle_search(self):
        if self._document is None:
            return
        if self.search_bar.isVisible():
            self._close_search()
        else:
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
        self._search_pages = self._search.iter_pages(query)
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
        if self._continuous or not self._page_labels:
            return
        canvas = self._page_labels[0]
        if not isinstance(canvas, PageCanvas):
            return
        if self.measure_state.is_page_active():
            canvas.setCursor(Qt.CursorShape.CrossCursor)
            return
        if self.redaction_state.is_page_active() or self.area_pick_state.is_page_active():
            canvas.setCursor(Qt.CursorShape.CrossCursor)
            return
        if not self.annotation_state.is_page_active() or self.annotation_state.active_tool() is None:
            canvas.setCursor(Qt.CursorShape.IBeamCursor)  # arrastar seleciona texto
            return
        tool = self.annotation_state.active_tool()
        if tool in _DRAWING_TOOLS:
            canvas.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == "select":
            canvas.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            canvas.setCursor(Qt.CursorShape.ArrowCursor)

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
            widget = self._form_widget_at(self._current_page, self._widget_point_to_pdf(self._current_page, x, y))
            if widget is not None:
                self._edit_form_widget(widget)
                return
            self._clear_text_selection()
            self._selection_start_pdf = self._widget_point_to_pdf(self._current_page, x, y)
            self._selection_base = QPixmap(self._page_labels[0].pixmap())
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
            self._update_text_selection(self._widget_point_to_pdf(self._current_page, x, y))
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
            painter.setPen(QPen(QColor("#ff5252"), 2, Qt.PenStyle.DashLine))
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
            self._update_text_selection(self._widget_point_to_pdf(self._current_page, x, y))
            self._selection_start_pdf = None
            self._selection_base = None
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
        if self._document is None or self._continuous:
            return False
        if self.measure_state.is_page_active() or self.redaction_state.is_page_active():
            return False
        if self.area_pick_state.is_page_active():
            return False
        return not self.annotation_state.is_page_active() or self.annotation_state.active_tool() is None

    def _update_text_selection(self, end_pdf):
        page_index = self._current_page
        with PDFIUM_LOCK:
            page = self._document[page_index]
            textpage = page.get_textpage()
            try:
                start_index = textpage.get_index(*self._selection_start_pdf, 6, 6)
                end_index = textpage.get_index(end_pdf[0], end_pdf[1], 6, 6)
                if start_index is None or end_index is None or start_index < 0 or end_index < 0:
                    self._text_selection, self._selection_rects = None, []
                else:
                    lo, hi = sorted((start_index, end_index))
                    count = hi - lo + 1
                    self._text_selection = (page_index, lo, count)
                    self._selection_rects = [textpage.get_rect(i) for i in range(textpage.count_rects(lo, count))]
            finally:
                textpage.close()
                page.close()
        base = self._selection_base or self._page_labels[0].pixmap()
        if base is None:
            return
        preview = QPixmap(base)
        painter = QPainter(preview)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_TEXT_SELECTION_COLOR)
        for rect in self._selection_rects:
            painter.drawRect(self._user_rect_to_screen(page_index, rect))
        painter.end()
        self._page_labels[0].setPixmap(preview)

    def _clear_text_selection(self):
        had_selection = self._text_selection is not None
        self._text_selection, self._selection_rects = None, []
        if had_selection and not self._continuous and self._page_labels:
            self._show_single_page(self._current_page)

    def selected_text(self) -> str:
        if self._text_selection is None or self._document is None:
            return ""
        page_index, start, count = self._text_selection
        with PDFIUM_LOCK:
            page = self._document[page_index]
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range(start, count)
            finally:
                textpage.close()
                page.close()

    def copy_selected_text(self):
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
        if self._continuous or not widgets:
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

    def _field_screen_rect(self, widget: FormWidget) -> QRectF:
        canvas = self._page_labels[0]
        assert isinstance(canvas, PageCanvas)  # campos só no modo página única
        rect = self._user_rect_to_screen(widget.page_index, widget.rect).normalized()
        return rect.translated(canvas.pixmap_offset())

    def _choose_option(self, widget: FormWidget) -> str | None:
        menu = QMenu(self)
        for value, text in widget.options:
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(value == widget.value)
            action.setData(value)
        canvas = self._page_labels[0]
        chosen = menu.exec(canvas.mapToGlobal(self._field_screen_rect(widget).bottomLeft().toPoint()))
        return None if chosen is None else chosen.data()

    def _open_field_editor(self, widget: FormWidget):
        # shortcut: campo de várias linhas é editado numa linha só; usar um QPlainTextEdit
        # se aparecerem formulários que dependam de quebras de linha.
        canvas = self._page_labels[0]
        rect = self._field_screen_rect(widget)
        editor = QLineEdit(widget.value, canvas)
        font = editor.font()
        font.setPixelSize(max(8, int(min(rect.height() * 0.7, 12 * self._scale))))
        editor.setFont(font)
        editor.setGeometry(rect.toAlignedRect())
        self._field_editor = (editor, widget)
        editor.editingFinished.connect(self._finish_field_edit)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), editor)
        escape.setContext(Qt.ShortcutContext.WidgetShortcut)
        escape.activated.connect(lambda: self._finish_field_edit(commit=False))
        editor.show()
        editor.setFocus()
        editor.selectAll()

    def _finish_field_edit(self, commit: bool = True):
        if self._field_editor is None:
            return
        (editor, widget), self._field_editor = self._field_editor, None
        text = editor.text()
        editor.hide()  # dispara editingFinished de novo, que já não acha editor aberto
        editor.deleteLater()
        if commit and text != widget.value:
            self._fill_form_fields({widget.name: text})

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
