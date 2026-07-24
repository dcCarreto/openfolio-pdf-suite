"""Widget central: visualizador de PDF com miniaturas, zoom, página única/rolagem
contínua e busca de texto."""

import pypdfium2 as pdfium
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.viewer.render import render_page
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


class PdfViewer(QWidget):
    """Mostra o PDF atualmente aberto na sessão compartilhada; não edita nada."""

    def __init__(self, session: DocumentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._document = None
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

        self._build_ui()
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._toggle_search)

        session.path_changed.connect(self._reload)
        if session.path():
            self._reload()

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
        self.content_stack.addWidget(self.scroll_area)

        body_layout.addWidget(self.content_stack, 1)
        layout.addWidget(body, 1)

        self._set_document_controls_enabled(False)

    def _build_empty_state(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        label = QLabel(tr("Nenhum PDF aberto"))
        label.setObjectName("pageSubtitle")
        open_button = QPushButton(tr("Abrir PDF..."))
        open_button.clicked.connect(self._browse_open)

        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return widget

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("viewerToolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        open_button = self._tool_button(build_open_icon(), tr("Abrir PDF..."))
        open_button.clicked.connect(self._browse_open)
        layout.addWidget(open_button)
        layout.addSpacing(10)

        prev_button = self._tool_button(build_prev_page_icon(), tr("Página anterior"))
        prev_button.clicked.connect(self._go_prev)
        next_button = self._tool_button(build_next_page_icon(), tr("Próxima página"))
        next_button.clicked.connect(self._go_next)
        self.page_indicator = QLabel()
        layout.addWidget(prev_button)
        layout.addWidget(self.page_indicator)
        layout.addWidget(next_button)
        layout.addSpacing(10)

        zoom_out_button = self._tool_button(build_zoom_out_icon(), tr("Diminuir zoom"))
        zoom_out_button.clicked.connect(self._zoom_out)
        zoom_in_button = self._tool_button(build_zoom_in_icon(), tr("Aumentar zoom"))
        zoom_in_button.clicked.connect(self._zoom_in)
        fit_width_button = self._tool_button(build_fit_width_icon(), tr("Ajustar à largura"))
        fit_width_button.clicked.connect(self._fit_width)
        self._zoom_label = QLabel(f"{int(self._scale * 100)}%")
        layout.addWidget(zoom_out_button)
        layout.addWidget(self._zoom_label)
        layout.addWidget(zoom_in_button)
        layout.addWidget(fit_width_button)
        layout.addSpacing(10)

        self.single_page_button = self._tool_button(build_single_page_icon(), tr("Página única"))
        self.single_page_button.setCheckable(True)
        self.single_page_button.setChecked(True)
        self.single_page_button.clicked.connect(lambda: self._set_continuous(False))

        self.continuous_button = self._tool_button(
            build_continuous_page_icon(), tr("Rolagem contínua")
        )
        self.continuous_button.setCheckable(True)
        self.continuous_button.clicked.connect(lambda: self._set_continuous(True))

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.single_page_button)
        self._mode_group.addButton(self.continuous_button)
        layout.addWidget(self.single_page_button)
        layout.addWidget(self.continuous_button)
        layout.addSpacing(10)

        self.thumbnails_button = self._tool_button(build_thumbnails_icon(), tr("Miniaturas"))
        self.thumbnails_button.setCheckable(True)
        self.thumbnails_button.setChecked(True)
        self.thumbnails_button.clicked.connect(self._toggle_thumbnails)
        layout.addWidget(self.thumbnails_button)

        search_button = self._tool_button(build_search_icon(), tr("Buscar"))
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
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
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
        if self._document is not None:
            self._document.close()
            self._document = None

        if not path:
            self.content_stack.setCurrentIndex(0)
            self.thumbnail_list.hide()
            self._set_document_controls_enabled(False)
            self._update_page_indicator()
            return

        self._document = pdfium.PdfDocument(path)
        self._search = DocumentSearch(self._document)
        self._matches = []
        self._current_match = -1
        self._current_page = 0
        self.search_bar.hide()

        self._set_document_controls_enabled(True)
        self.thumbnail_list.load_document(self._document)
        self.thumbnail_list.setVisible(self._show_thumbnails)
        self.content_stack.setCurrentIndex(1)
        self._rebuild_canvas()

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
            for index in range(len(self._document)):
                label = self._make_placeholder_label(index)
                vlayout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
                self._page_labels.append(label)
                self._page_tops.append(offset)
                offset += label.height() + spacing
            vlayout.addStretch()

            self.scroll_area.setWidget(container)
            self._update_visible_pages()
        else:
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._page_labels = [label]
            self.scroll_area.setWidget(label)
            self._show_single_page(self._current_page)

        self._update_page_indicator()

    def _make_placeholder_label(self, index: int) -> QLabel:
        page = self._document[index]
        width_pt, height_pt = page.get_size()
        label = QLabel()
        label.setFixedSize(max(1, int(width_pt * self._scale)), max(1, int(height_pt * self._scale)))
        label.setStyleSheet("background-color: white;")
        return label

    def _show_single_page(self, index: int):
        if self._document is None or not (0 <= index < len(self._document)):
            return
        self._current_page = index
        pixmap = render_page(self._document[index], self._scale)
        pixmap = self._with_highlight(pixmap, index)
        self._page_labels[0].setPixmap(pixmap)
        self._page_labels[0].resize(pixmap.size())
        self.thumbnail_list.select_page(index)
        self._update_page_indicator()

    def _render_page_into_label(self, index: int, label: QLabel):
        pixmap = render_page(self._document[index], self._scale)
        pixmap = self._with_highlight(pixmap, index)
        label.setPixmap(pixmap)
        self._rendered_pages.add(index)

    def _with_highlight(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        if not (0 <= self._current_match < len(self._matches)):
            return pixmap
        match = self._matches[self._current_match]
        if match.page_index != page_index:
            return pixmap

        _, page_height = self._document[page_index].get_size()
        highlighted = QPixmap(pixmap)
        painter = QPainter(highlighted)
        painter.setBrush(_HIGHLIGHT_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        x = match.left * self._scale
        width = (match.right - match.left) * self._scale
        top_y = (page_height - match.top) * self._scale
        height = (match.top - match.bottom) * self._scale
        painter.drawRect(QRectF(x, top_y, width, height))
        painter.end()
        return highlighted

    def _update_visible_pages(self):
        if not self._continuous or self._document is None or not self._page_labels:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        viewport_top = scrollbar.value()
        viewport_height = self.scroll_area.viewport().height()
        viewport_bottom = viewport_top + viewport_height
        buffer = viewport_height

        current_page = 0
        for index, label in enumerate(self._page_labels):
            label_top = self._page_tops[index]
            label_bottom = label_top + label.height()
            if label_top <= viewport_top:
                current_page = index
            if label_bottom >= viewport_top - buffer and label_top <= viewport_bottom + buffer:
                if index not in self._rendered_pages:
                    self._render_page_into_label(index, label)

        self._current_page = current_page
        self.thumbnail_list.select_page(current_page)
        self._update_page_indicator()

    def _scroll_to_page(self, index: int):
        if 0 <= index < len(self._page_tops):
            self.scroll_area.verticalScrollBar().setValue(self._page_tops[index])

    def _update_page_indicator(self):
        if self._document is None:
            self.page_indicator.setText("")
            return
        total = len(self._document)
        self.page_indicator.setText(
            tr("Página {current} de {total}").format(current=self._current_page + 1, total=total)
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
        last = len(self._document) - 1
        if self._continuous:
            self._scroll_to_page(min(last, self._current_page + 1))
        else:
            self._show_single_page(min(last, self._current_page + 1))

    def _apply_zoom(self):
        self._zoom_label.setText(f"{int(self._scale * 100)}%")
        if self._document is None:
            return
        if self._continuous:
            self._rebuild_canvas()
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
        width_pt, _ = self._document[self._current_page].get_size()
        if width_pt <= 0:
            return
        viewport_width = self.scroll_area.viewport().width() - 24
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, viewport_width / width_pt))
        self._apply_zoom()

    def _set_continuous(self, continuous: bool):
        if continuous == self._continuous:
            return
        self._continuous = continuous
        if self._document is not None:
            self._rebuild_canvas()

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
        self.search_bar.hide()
        self._matches = []
        self._current_match = -1
        self._refresh_current_render()

    def _search_document(self, query: str):
        if self._document is None or self._search is None:
            return
        self._matches = self._search.find_all(query)
        self._current_match = 0 if self._matches else -1
        self.search_bar.set_count(1 if self._matches else 0, len(self._matches))
        if self._matches:
            self._jump_to_match(0)

    def _step_match(self, direction: int):
        if not self._matches:
            return
        self._current_match = (self._current_match + direction) % len(self._matches)
        self.search_bar.set_count(self._current_match + 1, len(self._matches))
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
