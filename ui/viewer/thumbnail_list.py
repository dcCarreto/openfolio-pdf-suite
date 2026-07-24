"""Painel de miniaturas de página do visualizador."""

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem

from ui.i18n import tr
from ui.viewer.render import render_page

_THUMBNAIL_SCALE = 0.2


class ThumbnailList(QListWidget):
    """Lista de miniaturas de página; emite page_selected(index) ao clicar em uma."""

    page_selected = Signal(int)

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
        self.setSpacing(6)
        self.setIconSize(QSize(96, 128))
        self.setGridSize(QSize(132, 156))
        self.setFixedWidth(150)
        self.currentRowChanged.connect(self._on_row_changed)

    def load_document(self, pdfium_document) -> None:
        self.blockSignals(True)
        self.clear()
        for index in range(len(pdfium_document)):
            page = pdfium_document[index]
            pixmap = render_page(page, _THUMBNAIL_SCALE)
            item = QListWidgetItem(tr("Página {number}").format(number=index + 1))
            item.setIcon(pixmap.scaledToWidth(96))
            self.addItem(item)
        self.blockSignals(False)

    def select_page(self, index: int) -> None:
        if 0 <= index < self.count():
            self.blockSignals(True)
            self.setCurrentRow(index)
            self.blockSignals(False)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.page_selected.emit(row)
