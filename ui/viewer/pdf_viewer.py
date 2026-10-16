"""Widget central: visualizador de PDF com miniaturas, zoom, página única/rolagem
contínua e busca de texto."""

import time

import pypdfium2 as pdfium
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.annotations import AnnotationSpec, spec_rect
from core.base import known_password, remember_password
from core.geometry import PageGeometry
from core.progress import PDFIUM_LOCK
from core.redaction import RedactionRect
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.measure_state import MeasureState, format_distance
from ui.redaction_state import RedactionState
from ui.viewer.page_canvas import PageCanvas
from ui.viewer.render import logical_size, render_page
from ui.viewer.search import DocumentSearch
from ui.viewer.search_bar import SearchBar
from ui.viewer.thumbnail_list import ThumbnailList
from ui.viewer.viewer_icons import (
    build_continuous_page_icon,
    build_fit_width_icon,
    build_next_page_icon,
    build_open_icon,
    build_prev_page_icon,
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
_HIGHLIGHT_COLOR = QColor(255, 235, 59, 110)
_DRAWING_TOOLS = ("highlight", "underline", "strikeout", "note", "ink", "stamp")
# Rolagem contínua: páginas a mais de N alturas de tela da área visível têm a imagem
# descartada (voltam a ser renderizadas se o usuário rolar até elas). Antes nenhuma página
# era liberada e a memória crescia sem limite ao rolar documentos longos.
_KEEP_RENDERED_SCREENS = 3
# Busca incremental: tempo máximo por fatia antes de devolver o controle à janela.
_SEARCH_SLICE_SECONDS = 0.03


class PdfViewer(QWidget):
    """Mostra o PDF atualmente aberto na sessão compartilhada; não edita nada."""

    def __init__(
        self,
        session: DocumentSession,
        annotation_state: AnnotationState,
        redaction_state: RedactionState,
        measure_state: MeasureState | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.session = session
        self.annotation_state = annotation_state
        self.redaction_state = redaction_state
        self.measure_state = measure_state or MeasureState()
        self._document = None
        self._geometries: dict[int, PageGeometry] = {}
        self._scale = _DEFAULT_SCALE
        self._continuous = False
        self._show_thumbnails = True
        self._current_page = 0
        self._search = None
        self._matches = []
        self._current_match = -1
        self._page_labels: list[QLabel] = []
        self._page_tops: list[int] = []
        self._rendered_pages: set[int] = set()
        self._document_dependent_widgets: list[QWidget] = []
        self._drag_start_pdf: tuple[float, float] | None = None
        self._ink_points_pdf: list[tuple[float, float]] = []
        self._ink_preview_base: QPixmap | None = None
        self._redaction_drag_start_pdf: tuple[float, float] | None = None
        self._measure_drag_start_pdf: tuple[float, float] | None = None
        self._measure_preview_base: QPixmap | None = None
        self._translatable_tooltips: list[tuple[QWidget, str]] = []
        # Rolagem contínua: (página, fração da altura dela) a mostrar no topo assim que o
        # layout novo existir (depois de zoom ou troca de modo).
        self._pending_scroll: tuple[int, float] | None = None
        self._search_pages = None  # gerador da busca em andamento
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(0)
        self._search_timer.timeout.connect(self._continue_search)

        self._build_ui()
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._toggle_search)

        session.path_changed.connect(self._reload)
        annotation_state.tool_changed.connect(self._on_markup_state_changed)
        annotation_state.pending_changed.connect(self._refresh_current_render)
        redaction_state.active_changed.connect(self._on_markup_state_changed)
        redaction_state.pending_changed.connect(self._refresh_current_render)
        redaction_state.selection_changed.connect(self._on_redaction_selection_changed)
        self.measure_state.active_changed.connect(self._on_markup_state_changed)
        self.measure_state.result_changed.connect(self._refresh_current_render)
        self.measure_state.unit_changed.connect(self._refresh_current_render)
        if session.path():
            self._reload()
        self._on_markup_state_changed()

    # -- construção da UI -------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        self.search_bar = SearchBar()
        self.search_bar.hide()
        self.search_bar.search_requested.connect(self._search_document)
        self.search_bar.next_requested.connect(lambda: self._step_match(1))
        self.search_bar.prev_requested.connect(lambda: self._step_match(-1))
        self.search_bar.closed.connect(self._close_search)
        layout.addWidget(self.search_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.thumbnail_list = ThumbnailList()
        self.thumbnail_list.page_selected.connect(self._on_thumbnail_selected)
        self.thumbnail_list.hide()
        body_layout.addWidget(self.thumbnail_list)

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
        layout.addSpacing(10)

        prev_button = self._tool_button(build_prev_page_icon(), "Página anterior")
        prev_button.clicked.connect(self._go_prev)
        next_button = self._tool_button(build_next_page_icon(), "Próxima página")
        next_button.clicked.connect(self._go_next)
        self.page_indicator = QLabel()
        layout.addWidget(prev_button)
        layout.addWidget(self.page_indicator)
        layout.addWidget(next_button)
        layout.addSpacing(10)

        zoom_out_button = self._tool_button(build_zoom_out_icon(), "Diminuir zoom")
        zoom_out_button.clicked.connect(self._zoom_out)
        zoom_in_button = self._tool_button(build_zoom_in_icon(), "Aumentar zoom")
        zoom_in_button.clicked.connect(self._zoom_in)
        fit_width_button = self._tool_button(build_fit_width_icon(), "Ajustar à largura")
        fit_width_button.clicked.connect(self._fit_width)
        self._zoom_label = QLabel(f"{int(self._scale * 100)}%")
        layout.addWidget(zoom_out_button)
        layout.addWidget(self._zoom_label)
        layout.addWidget(zoom_in_button)
        layout.addWidget(fit_width_button)
        layout.addSpacing(10)

        self.single_page_button = self._tool_button(build_single_page_icon(), "Página única")
        self.single_page_button.setCheckable(True)
        self.single_page_button.setChecked(True)
        self.single_page_button.clicked.connect(lambda: self._set_continuous(False))

        self.continuous_button = self._tool_button(build_continuous_page_icon(), "Rolagem contínua")
        self.continuous_button.setCheckable(True)
        self.continuous_button.clicked.connect(lambda: self._set_continuous(True))

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.single_page_button)
        self._mode_group.addButton(self.continuous_button)
        layout.addWidget(self.single_page_button)
        layout.addWidget(self.continuous_button)
        layout.addSpacing(10)

        self.thumbnails_button = self._tool_button(build_thumbnails_icon(), "Miniaturas")
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
            self.single_page_button,
            self.continuous_button,
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
            self.session.open(path)

    def _reload(self):
        path = self.session.path()
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
        self._search = DocumentSearch(self._document)
        self._matches = []
        self._current_match = -1
        self._current_page = 0
        self.search_bar.hide()
        self.annotation_state.clear_pending()
        self.redaction_state.clear_pending()
        self.measure_state.clear_result()

        self._set_document_controls_enabled(True)
        self.thumbnail_list.load_document(self._document)
        self.thumbnail_list.setVisible(self._show_thumbnails)
        self.content_stack.setCurrentIndex(1)
        self._rebuild_canvas()

    def _show_empty_state(self):
        self.content_stack.setCurrentIndex(0)
        self.thumbnail_list.hide()
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
                    QMessageBox.critical(
                        self,
                        tr("Abrir PDF"),
                        tr("Não foi possível abrir o PDF (pode estar corrompido): {error}").format(
                            error=exc
                        ),
                    )
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
                QMessageBox.critical(
                    self, tr("Abrir PDF"), tr("Não foi possível abrir o PDF: {error}").format(error=exc)
                )
                return None

    # -- renderização --------------------------------------------------------

    def _rebuild_canvas(self):
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
            for index in range(self._page_count()):
                label = self._make_placeholder_label(index)
                vlayout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
                self._page_labels.append(label)
                self._page_tops.append(offset)
                offset += label.height() + spacing
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

    def _make_placeholder_label(self, index: int) -> QLabel:
        with PDFIUM_LOCK:
            width_pt, height_pt = self._document.get_page_size(index)
        label = QLabel()
        label.setFixedSize(max(1, int(width_pt * self._scale)), max(1, int(height_pt * self._scale)))
        label.setStyleSheet("background-color: white;")
        return label

    def _render_with_overlays(self, index: int) -> QPixmap:
        with PDFIUM_LOCK:
            page = self._document[index]
            pixmap = render_page(page, self._scale, self.devicePixelRatioF())
            page.close()
        pixmap = self._with_highlight(pixmap, index)
        pixmap = self._with_pending_annotations(pixmap, index)
        pixmap = self._with_pending_redactions(pixmap, index)
        return self._with_measure_overlay(pixmap, index)

    def _show_single_page(self, index: int):
        if self._document is None or not (0 <= index < self._page_count()):
            return
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
        if not (0 <= self._current_match < len(self._matches)):
            return pixmap
        match = self._matches[self._current_match]
        if match.page_index != page_index:
            return pixmap

        highlighted = QPixmap(pixmap)
        painter = QPainter(highlighted)
        painter.setBrush(_HIGHLIGHT_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(
            self._user_rect_to_screen(page_index, (match.left, match.bottom, match.right, match.top))
        )
        painter.end()
        return highlighted

    # Tudo o que o visualizador guarda (anotações, áreas de redação, medições, ocorrências da
    # busca) fica no espaço do usuário do PDF — o mesmo do pdfium e das operações de core/.
    # A conversão de/para pixels passa sempre pela geometria da página, que considera
    # /Rotate e CropBox (ver core/geometry.py).

    def _geometry(self, page_index: int) -> PageGeometry:
        geometry = self._geometries.get(page_index)
        if geometry is None:
            with PDFIUM_LOCK:
                page = self._document[page_index]
                geometry = PageGeometry.from_pdfium_page(page)
                page.close()
            self._geometries[page_index] = geometry
        return geometry

    def _user_rect_to_screen(self, page_index: int, rect) -> QRectF:
        return QRectF(*self._geometry(page_index).user_rect_to_screen(rect, self._scale))

    def _with_pending_annotations(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        specs = [s for s in self.annotation_state.pending() if s.page_index == page_index]
        if not specs:
            return pixmap

        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for spec in specs:
            self._paint_pending_spec(painter, page_index, spec)
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
            self._paint_ink_stroke(painter, page_index, spec.points, color)
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
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, spec.text)

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

    def _paint_ink_stroke(self, painter: QPainter, page_index: int, points, color: QColor):
        pen = QPen(color, max(1.0, 2.5 * self._scale))
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
            if label_top <= viewport_top:
                current_page = index
            if label_bottom >= viewport_top - buffer and label_top <= viewport_bottom + buffer:
                if index not in self._rendered_pages:
                    self._render_page_into_label(index, label)
            elif index in self._rendered_pages and (
                label_bottom < viewport_top - keep or label_top > viewport_bottom + keep
            ):
                self._release_page(index)

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
        if self._document is None:
            self.page_indicator.setText("")
            return
        self.page_indicator.setText(
            tr("Página {current} de {total}").format(current=self._current_page + 1, total=self._page_count())
        )

    # -- navegação e zoom -----------------------------------------------------

    def _go_prev(self):
        if self._continuous:
            self._scroll_to_page(max(0, self._current_page - 1))
        else:
            self._show_single_page(max(0, self._current_page - 1))

    def _go_next(self):
        if self._document is None:
            return
        last = self._page_count() - 1
        if self._continuous:
            self._scroll_to_page(min(last, self._current_page + 1))
        else:
            self._show_single_page(min(last, self._current_page + 1))

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
        with PDFIUM_LOCK:
            width_pt, _ = self._document.get_page_size(self._current_page)
        if width_pt <= 0:
            return
        viewport_width = self.scroll_area.viewport().width() - 24
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, viewport_width / width_pt))
        self._apply_zoom()

    def _set_continuous(self, continuous: bool):
        if continuous == self._continuous:
            return
        page = self._current_page
        self._continuous = continuous
        if self._document is not None:
            self._rebuild_canvas()
            if continuous:
                self._scroll_to_page(page)  # continua na página em que o usuário estava

    def _toggle_thumbnails(self, checked: bool):
        self._show_thumbnails = checked
        self.thumbnail_list.setVisible(checked and self._document is not None)

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
        match = self._matches[match_index]
        if self._continuous:
            self._scroll_to_page(match.page_index)
            self._render_page_into_label(match.page_index, self._page_labels[match.page_index])
        else:
            self._show_single_page(match.page_index)

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
        )
        if drawing_active and self._continuous:
            self._set_continuous(False)
            if hasattr(self, "single_page_button"):
                self.single_page_button.setChecked(True)
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
        if self.redaction_state.is_page_active():
            canvas.setCursor(Qt.CursorShape.CrossCursor)
            return
        if not self.annotation_state.is_page_active():
            canvas.setCursor(Qt.CursorShape.ArrowCursor)
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
        if self._document is None or selected is None or not (0 <= selected.page_index < self._page_count()):
            self._refresh_current_render()
            return
        if self._continuous:
            self._scroll_to_page(selected.page_index)
            self._refresh_current_render()
        elif selected.page_index != self._current_page:
            self._show_single_page(selected.page_index)
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
        if not self.annotation_state.is_page_active():
            return
        tool = self.annotation_state.active_tool()
        if self._document is None or tool is None:
            return
        page_index = self._current_page
        pdf_point = self._widget_point_to_pdf(page_index, x, y)

        if tool == "select":
            self._erase_pending_at(page_index, pdf_point)
            return
        if tool == "ink":
            self._ink_points_pdf = [pdf_point]
            # Congela o pixmap já renderizado (sem o traço em progresso) como base do
            # preview: cada movimento do mouse só repinta por cima dessa cópia, em vez de
            # re-renderizar a página inteira via pdfium a cada evento.
            self._ink_preview_base = QPixmap(self._page_labels[0].pixmap())
            return
        if tool in ("highlight", "underline", "strikeout"):
            self._drag_start_pdf = pdf_point
            return
        if tool == "note":
            self._prompt_note(page_index, pdf_point)
            return
        if tool == "stamp":
            self._place_stamp(page_index, pdf_point)
            return

    def _on_canvas_moved(self, x: float, y: float):
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
        self._paint_ink_stroke(painter, page_index, self._ink_points_pdf, color)
        painter.end()
        self._page_labels[0].setPixmap(preview)

    def _on_canvas_released(self, x: float, y: float):
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

        tool = self.annotation_state.active_tool()
        page_index = self._current_page
        pdf_point = self._widget_point_to_pdf(page_index, x, y)

        if tool == "ink":
            if len(self._ink_points_pdf) >= 2:
                self.annotation_state.add_pending(
                    AnnotationSpec(
                        page_index=page_index,
                        kind="ink",
                        color=self.annotation_state.active_color(),
                        points=list(self._ink_points_pdf),
                    )
                )
            self._ink_points_pdf = []
            self._ink_preview_base = None
            return

        if tool in ("highlight", "underline", "strikeout") and self._drag_start_pdf is not None:
            self._finish_text_markup(page_index, self._drag_start_pdf, pdf_point, tool)
            self._drag_start_pdf = None

    def _finish_text_markup(self, page_index: int, start_pdf, end_pdf, tool: str):
        with PDFIUM_LOCK:
            quads = self._text_quads(page_index, start_pdf, end_pdf)

        if not quads:
            return
        self.annotation_state.add_pending(
            AnnotationSpec(
                page_index=page_index,
                kind=tool,
                color=self.annotation_state.active_color(),
                quads=quads,
            )
        )

    def _text_quads(self, page_index: int, start_pdf, end_pdf) -> list:
        """Retângulos do texto entre os dois pontos (chamar com `PDFIUM_LOCK`)."""
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
                    rotation=self._geometry(page_index).rotation,
                )
            )

    def _place_stamp(self, page_index: int, pdf_point):
        self.annotation_state.add_pending(
            AnnotationSpec(
                page_index=page_index,
                kind="stamp",
                color=self.annotation_state.active_color(),
                position=pdf_point,
                text=self.annotation_state.stamp_text(),
                rotation=self._geometry(page_index).rotation,
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
