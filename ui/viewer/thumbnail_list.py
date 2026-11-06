"""Painel de miniaturas de página do visualizador."""

from PySide6.QtCore import QItemSelectionModel, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from core.progress import PDFIUM_LOCK
from ui import theme
from ui.i18n import tr
from ui.viewer.page_renderer import THUMBNAIL, PageRenderer
from ui.viewer.render import render_image, to_pixmap

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

    Só as miniaturas à vista (e as de uma tela antes e depois) são renderizadas, na thread de
    render do visualizador, depois das páginas da tela. Antes todas eram renderizadas ao
    abrir o documento, na thread da interface, uma por volta do laço de eventos: num
    escaneado de 80 páginas a janela engasgava por quatro segundos, e num documento longo as
    miniaturas que ninguém ia ver consumiam o processador.
    """

    page_selected = Signal(int)
    pages_selected = Signal(list)  # páginas selecionadas (Ctrl/Shift+clique), a partir de 0

    def __init__(self, renderer: PageRenderer | None = None, parent=None):
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

        self._own_renderer = renderer is None
        self._renderer = renderer if renderer is not None else PageRenderer(self)
        self._renderer.rendered.connect(self._on_rendered)
        self._document = None
        self._pending: set[int] = set()
        self._thumbnails: dict[int, QPixmap] = {}
        self._placeholder = QPixmap(_ICON_SIZE.width(), _ICON_SIZE.width() * 4 // 3)
        self._placeholder.fill(QColor("white"))

        # Os pedidos saem depois que a rolagem e o layout assentam (vários eventos, um pedido).
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._request_visible)
        # Sem argumento: ligado direto, `valueChanged(int)` cairia em `start(msec)` e a
        # posição da barra viraria o intervalo.
        self.verticalScrollBar().valueChanged.connect(lambda _value: self._timer.start())

    def load_document(self, pdfium_document) -> None:
        self._timer.stop()
        self.blockSignals(True)
        self.clear()
        self._document = pdfium_document
        if self._own_renderer:
            self._renderer.set_document(pdfium_document)
        with PDFIUM_LOCK:
            total = len(pdfium_document)
        icon = QIcon(self._placeholder)
        for index in range(total):
            item = QListWidgetItem(tr("Página {number}").format(number=index + 1))
            item.setIcon(icon)
            self.addItem(item)
        self.blockSignals(False)
        self._pending = set(range(total))
        self._thumbnails = {}
        self._timer.start()

    def clear_document(self) -> None:
        """Esquece o documento (fechado pelo visualizador): nada mais é renderizado."""
        self._timer.stop()
        self._document = None
        self._pending = set()
        self._thumbnails = {}
        self._renderer.retain(lambda key: key[0] != "thumb")
        if self._own_renderer:
            self._renderer.set_document(None)
        self.clear()

    def retranslate(self) -> None:
        for index in range(self.count()):
            self.item(index).setText(tr("Página {number}").format(number=index + 1))

    def pending_count(self) -> int:
        return len(self._pending)

    def thumbnail(self, index: int) -> QPixmap | None:
        """A miniatura da página, se já foi renderizada (a prévia de uma página pesada)."""
        return self._thumbnails.get(index)

    def render_all(self) -> None:
        """Renderiza o que falta de uma vez, aqui mesmo (usado nos testes)."""
        if self._document is None:
            return
        for index in sorted(self._pending):
            with PDFIUM_LOCK:
                page = self._document[index]
                try:
                    width_pt = page.get_width()
                    scale = _ICON_SIZE.width() / width_pt if width_pt > 0 else _THUMBNAIL_SCALE
                    image = render_image(page, scale, self.devicePixelRatioF())
                finally:
                    page.close()
            self._set_thumbnail(index, to_pixmap(image))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._timer.start()

    def _visible_rows(self) -> range:
        first = self.indexAt(QPoint(10, 10)).row()
        last = self.indexAt(QPoint(10, self.viewport().height() - 10)).row()
        if first < 0:
            return range(0)
        if last < 0:
            last = self.count() - 1
        return range(first, last + 1)

    def _request_visible(self) -> None:
        """Pede as miniaturas à vista e as de uma tela antes e depois; as que saíram de
        perto deixam a fila."""
        if self._document is None or not self._pending or not self.isVisible():
            return
        rows = self._visible_rows() or range(min(self.count(), 8))
        margin = max(4, len(rows))
        nearby = range(max(0, rows.start - margin), min(self.count(), rows.stop + margin))
        wanted = set()
        ratio = self.devicePixelRatioF()
        for index in sorted(nearby, key=lambda row: (row not in rows, row)):
            if index in self._pending:
                key = ("thumb", index)
                wanted.add(key)
                priority = THUMBNAIL if index in rows else THUMBNAIL + 1
                self._renderer.request(
                    key, index, _THUMBNAIL_SCALE, ratio, priority=priority, fit_width=_ICON_SIZE.width()
                )
        self._renderer.retain(lambda key: key[0] != "thumb" or key in wanted)

    def _on_rendered(self, tagged_key, image, _info) -> None:
        key = self._renderer.accept(tagged_key)
        if key is None or key[0] != "thumb" or self._document is None:
            return
        if key[1] in self._pending:
            self._set_thumbnail(key[1], to_pixmap(image))

    def _set_thumbnail(self, index: int, pixmap: QPixmap) -> None:
        self._pending.discard(index)
        self._thumbnails[index] = pixmap
        item = self.item(index)
        if item is not None:
            item.setIcon(QIcon(pixmap))

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
