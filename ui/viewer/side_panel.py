"""Painel lateral do visualizador: miniaturas, marcadores (sumário) e anexos (M12).

Antes só havia as miniaturas: para navegar pelo sumário ou abrir um anexo era preciso ir
às abas Marcadores ou Anexos, que só listam o conteúdo. Aqui um clique num marcador vai à
página dele, e um duplo clique num anexo oferece salvá-lo.

As abas Marcadores e Anexos só aparecem quando o documento tem o que mostrar.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QListWidget, QListWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem

from core.attachments import ListAttachments, SaveAttachment
from core.bookmarks import ListOutline
from ui.errors import show_error
from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder

logger = logging.getLogger(__name__)


class DocumentSidePanel(QTabWidget):
    page_requested = Signal(int)

    def __init__(self, thumbnail_list, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerSidePanel")
        self.setDocumentMode(True)
        # Abas na lateral, com o texto na vertical: os três nomes cabem sem tirar largura
        # do visualizador.
        self.setTabPosition(QTabWidget.TabPosition.West)
        self.setFixedWidth(178)
        self._path: str | None = None

        self.thumbnail_list = thumbnail_list
        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.itemClicked.connect(self._on_outline_clicked)
        self.attachments_list = QListWidget()
        self.attachments_list.itemDoubleClicked.connect(self._on_attachment_activated)

        self.addTab(self.thumbnail_list, "")
        self.addTab(self.outline_tree, "")
        self.addTab(self.attachments_list, "")
        self.retranslate()
        self._update_tabs()

    def retranslate(self):
        self.setTabText(0, tr("Páginas"))
        self.setTabText(1, tr("Marcadores"))
        self.setTabText(2, tr("Anexos"))
        self.setTabToolTip(0, tr("Miniaturas (Ctrl ou Shift + clique seleciona várias)"))
        self.attachments_list.setToolTip(tr("Duplo clique para salvar o anexo"))

    def load(self, path: str) -> None:
        """Lê o sumário e os anexos do documento (as miniaturas são carregadas à parte)."""
        self._path = path
        self.outline_tree.clear()
        self.attachments_list.clear()
        try:
            outline = ListOutline().run(path)
        except Exception:
            logger.debug("Sem sumário legível em %s", path, exc_info=True)
            outline = []
        parents: list[QTreeWidgetItem] = []
        for entry in outline:
            item = QTreeWidgetItem([entry.title or tr("(sem título)")])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.page_index)
            if entry.page_index is not None:
                item.setToolTip(0, tr("Página {page}").format(page=entry.page_index + 1))
            del parents[entry.level :]
            if parents:
                parents[-1].addChild(item)
            else:
                self.outline_tree.addTopLevelItem(item)
            parents.append(item)
        self.outline_tree.expandToDepth(0)

        try:
            attachments = ListAttachments().run(path)
        except Exception:
            logger.debug("Sem anexos legíveis em %s", path, exc_info=True)
            attachments = []
        for info in attachments:
            item = QListWidgetItem(f"{info.name} ({_size(info.size)})")
            item.setData(Qt.ItemDataRole.UserRole, info.name)
            self.attachments_list.addItem(item)
        self._update_tabs()

    def clear(self) -> None:
        self._path = None
        self.outline_tree.clear()
        self.attachments_list.clear()
        self._update_tabs()

    def _update_tabs(self):
        self.setTabVisible(1, self.outline_tree.topLevelItemCount() > 0)
        self.setTabVisible(2, self.attachments_list.count() > 0)
        visible = sum(self.isTabVisible(index) for index in range(self.count()))
        self.tabBar().setVisible(visible > 1)
        if not self.isTabVisible(self.currentIndex()):
            self.setCurrentIndex(0)

    def _on_outline_clicked(self, item: QTreeWidgetItem, _column: int):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            self.page_requested.emit(int(page))

    def _on_attachment_activated(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name or not self._path:
            return
        target, _ = QFileDialog.getSaveFileName(self, tr("Salvar anexo"), str(Path(start_folder()) / Path(name).name))
        if not target:
            return
        try:
            SaveAttachment().run(self._path, name, target)
        except Exception as exc:
            show_error(self, tr("Salvar anexo"), tr("Não foi possível salvar o anexo: {error}"), exc)
            return
        remember_folder_of(target)


def _size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
