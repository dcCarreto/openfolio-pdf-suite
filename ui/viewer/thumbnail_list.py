"""Painel de miniaturas de página do visualizador."""

from PySide6.QtCore import QItemSelectionModel, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from core.progress import PDFIUM_LOCK
from ui import theme
from ui.i18n import tr
from ui.viewer.render import render_page

_THUMBNAIL_SCALE = 0.2
_ICON_SIZE = QSize(104, 134)


class _ThumbnailDelegate(QStyledItemDelegate):
    """A página com sombra pintada e o número embaixo; a atual (e as selecionadas) com o
    contorno no acento e o número em negrito, para não depender só da cor."""

    def paint(self, painter: QPainter, option, index):
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        pixmap = icon.pixmap(_ICON_SIZE) if isinstance(icon, QIcon) else None
        size = pixmap.deviceIndependentSize().toSize() if pixmap is not None and not pixmap.isNull() else _ICON_SIZE
        size = size.scaled(_ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio)
        page = QRectF(cell.center().x() - size.width() / 2, cell.top() + 8, size.width(), size.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawRoundedRect(page.translated(0, 2).adjusted(-1, 0, 1, 1), 2, 2)  # sombra
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page)
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(page, pixmap, QRectF(pixmap.rect()))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.drawRoundedRect(page.adjusted(-3, -3, 3, 3), 4, 4)
        font = QFont(option.font)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(t["accent_strong" if selected else "text2"]))
        label = QRect(cell.left(), int(page.bottom()) + 6, cell.width(), 16)
        painter.drawText(label, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, str(index.row() + 1))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(_ICON_SIZE.width() + 24, _ICON_SIZE.height() + 34)


class ThumbnailList(QListWidget):
    """Lista de miniaturas de página; emite page_selected(index) ao clicar em uma.

    As miniaturas são renderizadas aos poucos, uma por volta do laço de eventos, começando
    pelas que estão à vista: antes todas eram renderizadas de uma vez ao abrir o documento
    (0,6 s num PDF de 400 páginas de texto, muito mais em escaneados), com a janela travada.
    """

    page_selected = Signal(int)
    pages_selected = Signal(list)  # páginas selecionadas (Ctrl/Shift+clique), a partir de 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("thumbnailList")
        # Modo ícone com fluxo de cima para baixo: legenda ("Página N") abaixo da
        # miniatura em vez de ao lado, já que a coluna é estreita demais para as
        # duas coisas lado a lado.
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setIconSize(_ICON_SIZE)
        self.setGridSize(QSize(_ICON_SIZE.width() + 24, _ICON_SIZE.height() + 34))
        self.setItemDelegate(_ThumbnailDelegate(self))
        # A largura vem do painel lateral (ui/viewer/side_panel.py); a coluna é uma só.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.currentRowChanged.connect(self._on_row_changed)
        # Ctrl/Shift+clique seleciona várias páginas, que as ferramentas usam como entrada.
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.itemSelectionChanged.connect(self._on_selection_changed)

        self._document = None
        self._pending: set[int] = set()
        self._placeholder = QPixmap(_ICON_SIZE.width(), _ICON_SIZE.width() * 4 // 3)
        self._placeholder.fill(QColor("white"))

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_next)

    def load_document(self, pdfium_document) -> None:
        self._timer.stop()
        self.blockSignals(True)
        self.clear()
        self._document = pdfium_document
        with PDFIUM_LOCK:
            total = len(pdfium_document)
        for index in range(total):
            item = QListWidgetItem(tr("Página {number}").format(number=index + 1))
            item.setIcon(self._placeholder)
            self.addItem(item)
        self.blockSignals(False)
        self._pending = set(range(total))
        if self._pending:
            self._timer.start()

    def clear_document(self) -> None:
        """Esquece o documento (fechado pelo visualizador): nada mais é renderizado."""
        self._timer.stop()
        self._document = None
        self._pending = set()
        self.clear()

    def retranslate(self) -> None:
        for index in range(self.count()):
            self.item(index).setText(tr("Página {number}").format(number=index + 1))

    def pending_count(self) -> int:
        return len(self._pending)

    def render_all(self) -> None:
        """Renderiza o que falta de uma vez (usado nos testes)."""
        while self._pending:
            self._render_next()

    def _visible_rows(self) -> range:
        first = self.indexAt(QPoint(10, 10)).row()
        last = self.indexAt(QPoint(10, self.viewport().height() - 10)).row()
        if first < 0:
            return range(0)
        if last < 0:
            last = self.count() - 1
        return range(first, last + 1)

    def _render_next(self) -> None:
        if self._document is None or not self._pending:
            self._timer.stop()
            return
        index = next((row for row in self._visible_rows() if row in self._pending), min(self._pending))
        self._pending.discard(index)
        with PDFIUM_LOCK:
            page = self._document[index]
            width_pt = page.get_width()
            # Já na largura do ícone: sem reamostrar depois (e nítido em telas com escala).
            scale = _ICON_SIZE.width() / width_pt if width_pt > 0 else _THUMBNAIL_SCALE
            pixmap = render_page(page, scale, self.devicePixelRatioF())
            page.close()
        item = self.item(index)
        if item is not None:
            item.setIcon(QIcon(pixmap))
        if not self._pending:
            self._timer.stop()

    def select_page(self, index: int) -> None:
        """Marca a página atual (navegação pelo visualizador). Com várias páginas
        selecionadas pelo usuário, a seleção dele não é desfeita."""
        if 0 <= index < self.count():
            command = (
                QItemSelectionModel.SelectionFlag.NoUpdate
                if len(self.selectedItems()) > 1
                else QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            self.blockSignals(True)
            self.setCurrentRow(index, command)
            self.blockSignals(False)

    def selected_pages(self) -> list[int]:
        return sorted(self.row(item) for item in self.selectedItems())

    def _on_selection_changed(self) -> None:
        self.pages_selected.emit(self.selected_pages())

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.page_selected.emit(row)
