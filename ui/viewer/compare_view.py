"""Comparação lado a lado (A10): as duas versões em colunas, com as diferenças de texto
destacadas nas duas e a rolagem de uma acompanhando a da outra."""

import bisect
from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.base import known_password
from core.compare import Box, DocumentDiff, TextChange
from core.geometry import PageGeometry
from core.progress import PDFIUM_LOCK
from ui.i18n import tr
from ui.page_ranges import format_page_ranges
from ui.theme import apply_titlebar
from ui.viewer.render import render_page
from ui.viewer.viewer_icons import build_next_page_icon, build_prev_page_icon, build_zoom_in_icon, build_zoom_out_icon

COLORS = {
    "removed": QColor(229, 57, 53, 80),
    "added": QColor(67, 160, 71, 80),
    "changed": QColor(251, 140, 0, 80),
}
_CURRENT_PEN = QColor(213, 0, 0)
_MARGIN = 12
_MIN_SCALE, _MAX_SCALE, _ZOOM_STEP = 0.3, 4.0, 0.15
_KEEP_RENDERED_SCREENS = 3
_PREVIEW_CHARS = 60


def _open(path: str):
    # Lido para a memória: o arquivo (talvez uma versão de trabalho do documento) não fica
    # preso pela janela e pode ser apagado ao desfazer ou fechar o documento.
    return pdfium.PdfDocument(Path(path).read_bytes(), password=known_password(path))


class ComparePane(QWidget):
    """Uma das versões: as páginas em rolagem contínua, renderizadas só perto da área
    visível, com as diferenças pintadas por cima."""

    scrolled = Signal()

    def __init__(self, title: str, path: str, parent=None):
        super().__init__(parent)
        with PDFIUM_LOCK:
            self._document = _open(path)
            self._geometries = []
            for index in range(len(self._document)):
                page = self._document[index]
                self._geometries.append(PageGeometry.from_pdfium_page(page))
                page.close()
        self._scale = 1.0
        self._highlights: dict[int, list[tuple[Box, QColor, bool]]] = {}
        self._labels: list[QLabel] = []
        self._tops: list[int] = []
        self._rendered: dict[int, QPixmap] = {}  # página -> imagem sem os destaques
        self._pending_center: float | None = None

        self.title_label = QLabel(title)
        self.title_label.setToolTip(path)
        self.title_label.setStyleSheet("font-weight: bold; padding: 4px;")
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.valueChanged.connect(self._update_visible_pages)
        scrollbar.valueChanged.connect(self.scrolled)
        scrollbar.rangeChanged.connect(self._apply_pending_center)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title_label)
        layout.addWidget(self.scroll_area, 1)
        self._rebuild()

    def page_count(self) -> int:
        return len(self._geometries)

    def close_document(self):
        with PDFIUM_LOCK:
            self._document.close()

    def max_page_width(self) -> float:
        return max((geometry.width for geometry in self._geometries), default=0)

    def set_scale(self, scale: float):
        """Muda o zoom mantendo no centro o mesmo ponto do documento."""
        center = self.center_y() / self._scale
        self._scale = scale
        self._rebuild()
        self.scroll_center_to(center * scale)

    def set_highlights(self, highlights: dict[int, list[tuple[Box, QColor, bool]]]):
        self._highlights = highlights
        for index in self._rendered:
            self._paint(index)

    def _rebuild(self):
        self._rendered = {}
        self._labels, self._tops = [], []
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        layout.setSpacing(_MARGIN)
        offset = _MARGIN
        for geometry in self._geometries:
            label = QLabel()
            label.setFixedSize(max(1, int(geometry.width * self._scale)), max(1, int(geometry.height * self._scale)))
            label.setStyleSheet("background-color: white;")
            layout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
            self._labels.append(label)
            self._tops.append(offset)
            offset += label.height() + _MARGIN
        layout.addStretch()
        self.scroll_area.setWidget(container)
        self._update_visible_pages()

    def _update_visible_pages(self):
        top = self.scroll_area.verticalScrollBar().value()
        height = self.scroll_area.viewport().height()
        for index, label in enumerate(self._labels):
            label_top, label_bottom = self._tops[index], self._tops[index] + label.height()
            if label_bottom >= top - height and label_top <= top + 2 * height:
                if index not in self._rendered:
                    with PDFIUM_LOCK:
                        page = self._document[index]
                        self._rendered[index] = render_page(page, self._scale, self.devicePixelRatioF())
                        page.close()
                    self._paint(index)
            elif index in self._rendered and (
                label_bottom < top - _KEEP_RENDERED_SCREENS * height
                or label_top > top + (_KEEP_RENDERED_SCREENS + 1) * height
            ):
                del self._rendered[index]
                label.clear()

    def _paint(self, index: int):
        pixmap = QPixmap(self._rendered[index])
        painter = QPainter(pixmap)
        for box, color, current in self._highlights.get(index, []):
            rect = self._screen_rect(box).adjusted(-1, -1, 1, 1)
            painter.fillRect(rect, color)
            if current:
                painter.setPen(QPen(_CURRENT_PEN, 2))
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        painter.end()
        self._labels[index].setPixmap(pixmap)

    def _screen_rect(self, box: Box) -> QRectF:
        return QRectF(*self._geometries[box.page].user_rect_to_screen(box[1:], self._scale))

    # -- posição no documento (em pixels do conteúdo da rolagem) ------------------------

    def y_of(self, box: Box) -> float:
        return self._tops[box.page] + self._screen_rect(box).center().y()

    def center_y(self) -> float:
        if self._pending_center is not None:
            return self._pending_center
        return self.scroll_area.verticalScrollBar().value() + self.scroll_area.viewport().height() / 2

    def scroll_center_to(self, y: float):
        scrollbar = self.scroll_area.verticalScrollBar()
        target = int(y - self.scroll_area.viewport().height() / 2)
        # Logo depois de montar as páginas, a faixa da barra ainda não cresceu: a rolagem
        # acontece quando crescer (`_apply_pending_center`).
        self._pending_center = y if target > scrollbar.maximum() else None
        scrollbar.setValue(target)

    def _apply_pending_center(self, _minimum: int, _maximum: int):
        if self._pending_center is not None:
            self.scroll_center_to(self._pending_center)

    def show_box(self, box: Box):
        """Põe a caixa no centro da área visível (e na horizontal, se o zoom passa da largura)."""
        self.scroll_center_to(self.y_of(box))
        label = self._labels[box.page]
        center = self._screen_rect(box).center()
        self.scroll_area.ensureVisible(int(label.x() + center.x()), int(self.y_of(box)), 60, 0)


def describe_change(change: TextChange) -> str:
    def short(text: str) -> str:
        return text if len(text) <= _PREVIEW_CHARS else text[: _PREVIEW_CHARS - 1] + "…"

    page_a = change.anchor_a.page + 1 if change.anchor_a else None
    page_b = change.anchor_b.page + 1 if change.anchor_b else None
    pages = str(page_a or page_b) if page_a == page_b or not (page_a and page_b) else f"{page_a} → {page_b}"
    if change.kind == "removed":
        text = tr("removido “{a}”").format(a=short(change.text_a))
    elif change.kind == "added":
        text = tr("incluído “{b}”").format(b=short(change.text_b))
    else:
        text = tr("“{a}” → “{b}”").format(a=short(change.text_a), b=short(change.text_b))
    return tr("Pág. {pages}: {change}").format(pages=pages, change=text)


class CompareWindow(QWidget):
    """Janela com a lista de diferenças e as duas versões lado a lado."""

    def __init__(self, title_a: str, path_a: str, title_b: str, path_b: str, diff: DocumentDiff, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Comparação lado a lado — {a} × {b}").format(a=title_a, b=title_b))
        self.resize(1400, 900)
        self.diff = diff
        self._current = -1
        self._scale = 1.0
        self._syncing = False
        self._fitted = False

        self.pane_a = ComparePane(f"A: {title_a}", path_a)
        self.pane_b = ComparePane(f"B: {title_b}", path_b)
        self.pane_a.scrolled.connect(lambda: self._sync(self.pane_a, self.pane_b))
        self.pane_b.scrolled.connect(lambda: self._sync(self.pane_b, self.pane_a))

        self.changes_list = QListWidget()
        self.changes_list.addItems([describe_change(change) for change in diff.changes])
        self.changes_list.currentRowChanged.connect(self.go_to_change)

        self.summary_label = QLabel(self._summary())
        self.summary_label.setWordWrap(True)
        self.prev_button = QPushButton(build_prev_page_icon(), "")
        self.prev_button.setToolTip(tr("Diferença anterior (Shift+F3)"))
        self.prev_button.clicked.connect(lambda: self._step(-1))
        self.next_button = QPushButton(build_next_page_icon(), "")
        self.next_button.setToolTip(tr("Próxima diferença (F3)"))
        self.next_button.clicked.connect(lambda: self._step(1))
        self.counter_label = QLabel()
        zoom_out = QPushButton(build_zoom_out_icon(), "")
        zoom_out.setToolTip(tr("Diminuir zoom"))
        zoom_out.clicked.connect(lambda: self._zoom(self._scale - _ZOOM_STEP))
        zoom_in = QPushButton(build_zoom_in_icon(), "")
        zoom_in.setToolTip(tr("Aumentar zoom"))
        zoom_in.clicked.connect(lambda: self._zoom(self._scale + _ZOOM_STEP))
        for button in (self.prev_button, self.next_button):
            button.setEnabled(bool(diff.changes))

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.prev_button)
        toolbar.addWidget(self.counter_label)
        toolbar.addWidget(self.next_button)
        for kind, name in (("removed", tr("Removido de A")), ("added", tr("Incluído em B")), ("changed", tr("Alterado"))):
            # A cor do destaque sobre o papel branco, opaca: sobre o tema escuro, a
            # transparente ficaria escura.
            color = COLORS[kind]
            red, green, blue = (255 - (255 - value) * color.alpha() // 255 for value in color.getRgb()[:3])
            legend = QLabel(name)
            legend.setStyleSheet(
                f"background-color: rgb({red}, {green}, {blue}); color: black; padding: 2px 6px; border-radius: 3px;"
            )
            toolbar.addWidget(legend)
        toolbar.addStretch()
        toolbar.addWidget(zoom_out)
        toolbar.addWidget(zoom_in)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.summary_label)
        side_layout.addWidget(self.changes_list, 1)

        splitter = QSplitter()
        splitter.addWidget(side)
        splitter.addWidget(self.pane_a)
        splitter.addWidget(self.pane_b)
        splitter.setSizes([280, 560, 560])

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(splitter, 1)

        QShortcut(QKeySequence("F3"), self, activated=lambda: self._step(1))
        QShortcut(QKeySequence("Shift+F3"), self, activated=lambda: self._step(-1))
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self._zoom(self._scale + _ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom(self._scale - _ZOOM_STEP))

        self._update_sync_points()
        self._update_highlights()
        self._update_counter()
        apply_titlebar(self)

    def _summary(self) -> str:
        count = len(self.diff.changes)
        lines = [tr("{count} diferença(s) no texto.").format(count=count) if count else tr("Nenhuma diferença no texto.")]
        for side, pages in (("A", self.diff.pages_without_text_a), ("B", self.diff.pages_without_text_b)):
            if pages:
                lines.append(
                    tr("Páginas de {side} sem texto (escaneadas? faça o OCR antes): {pages}").format(
                        side=side, pages=format_page_ranges(pages)
                    )
                )
        lines.append(
            tr(
                "Imagens, formatação e cabeçalhos/rodapés repetidos em todas as páginas não entram "
                "na comparação; para eles, use \"Comparar visualmente\"."
            )
        )
        return "\n".join(lines)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self._fit_width)  # depois do layout: a largura das colunas já existe

    def _fit_width(self):
        widest = max(self.pane_a.max_page_width(), self.pane_b.max_page_width())
        available = min(pane.scroll_area.viewport().width() for pane in (self.pane_a, self.pane_b)) - 2 * _MARGIN
        if widest > 0 and available > 0:
            self._zoom(available / widest)
        if self.diff.changes and self._current < 0:
            self.changes_list.setCurrentRow(0)

    def _zoom(self, scale: float):
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, scale))
        self._syncing = True
        try:
            self.pane_a.set_scale(self._scale)
            self.pane_b.set_scale(self._scale)
        finally:
            self._syncing = False
        self._update_sync_points()

    def _update_sync_points(self):
        """Pares (y em A, y em B) das palavras iguais, ordenados por cada lado."""
        points = [(self.pane_a.y_of(box_a), self.pane_b.y_of(box_b)) for box_a, box_b in self.diff.matches]
        self._points_from_a = sorted(points)
        self._points_from_b = sorted((y_b, y_a) for y_a, y_b in points)

    def _sync(self, source: ComparePane, target: ComparePane):
        """Rola `target` até o trecho que corresponde ao centro de `source`."""
        if self._syncing:
            return
        points = self._points_from_a if source is self.pane_a else self._points_from_b
        y = source.center_y()
        if not points:
            y_target = y  # sem texto em comum: mesma posição
        else:
            index = bisect.bisect(points, (y, float("inf")))
            if index == 0:
                y_target = points[0][1] + y - points[0][0]
            elif index == len(points):
                y_target = points[-1][1] + y - points[-1][0]
            else:
                (x0, y0), (x1, y1) = points[index - 1], points[index]
                y_target = y0 + (y1 - y0) * (y - x0) / (x1 - x0) if x1 > x0 else y0
        self._syncing = True
        try:
            target.scroll_center_to(y_target)
        finally:
            self._syncing = False

    def _update_highlights(self):
        highlights: tuple[dict, dict] = ({}, {})
        for number, change in enumerate(self.diff.changes):
            color = COLORS[change.kind]
            current = number == self._current
            for side, boxes in zip(highlights, (change.boxes_a, change.boxes_b)):
                for box in boxes:
                    side.setdefault(box.page, []).append((box, color, current))
        self.pane_a.set_highlights(highlights[0])
        self.pane_b.set_highlights(highlights[1])

    def _update_counter(self):
        total = len(self.diff.changes)
        self.counter_label.setText(tr("{current} de {total}").format(current=self._current + 1 if total else 0, total=total))

    def _step(self, direction: int):
        if self.diff.changes:
            self.changes_list.setCurrentRow((self._current + direction) % len(self.diff.changes))

    def go_to_change(self, number: int):
        if not 0 <= number < len(self.diff.changes):
            return
        self._current = number
        change = self.diff.changes[number]
        self._update_highlights()
        self._update_counter()
        self._syncing = True
        try:
            for pane, anchor in ((self.pane_a, change.anchor_a), (self.pane_b, change.anchor_b)):
                if anchor is not None:
                    pane.show_box(anchor)
        finally:
            self._syncing = False

    def closeEvent(self, event):
        self.pane_a.close_document()
        self.pane_b.close_document()
        super().closeEvent(event)
