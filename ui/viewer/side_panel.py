"""Painel lateral do visualizador: miniaturas, marcadores (sumário) e anexos (M12).

Antes só havia as miniaturas: para navegar pelo sumário ou abrir um anexo era preciso ir
às abas Marcadores ou Anexos, que só listam o conteúdo. Aqui um clique num marcador vai à
página dele, e um duplo clique num anexo oferece salvá-lo.

As abas Marcadores e Anexos só aparecem quando o documento tem o que mostrar.
"""

import atexit
import logging
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QListWidget, QListWidgetItem, QMenu, QTabWidget, QTreeWidget, QTreeWidgetItem

from core.attachments import ListAttachments, SaveAttachment
from core.bookmarks import ListOutline
from ui.document_session import ATTACHMENT_FOLDER_PREFIX
from ui.errors import show_error
from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder

logger = logging.getLogger(__name__)


_TOP_ROLE = Qt.ItemDataRole.UserRole + 1
_URL_ROLE = Qt.ItemDataRole.UserRole + 2


class DocumentSidePanel(QTabWidget):
    destination_requested = Signal(int, object)  # página e a altura nela (ou None)
    url_requested = Signal(str)
    file_requested = Signal(str)  # um PDF anexado, já extraído, para abrir
    tabs_changed = Signal()  # uma aba apareceu ou sumiu (o documento tem marcadores, anexos?)
    visibility_changed = Signal(bool)  # mostrado ou escondido (o cabeçalho da aba acompanha)

    def __init__(self, thumbnail_list, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerSidePanel")
        self.setDocumentMode(True)
        # Abas na lateral, com o texto na vertical: os três nomes cabem sem tirar largura
        # do visualizador.
        self.setTabPosition(QTabWidget.TabPosition.West)
        self.setFixedWidth(178)
        self._path: str | None = None
        self._external_rail = False
        self._opened_attachments: dict[tuple[str, str], str] = {}  # o mesmo anexo não abre duas abas

        self.thumbnail_list = thumbnail_list
        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.itemClicked.connect(self._on_outline_clicked)
        self.outline_tree.itemActivated.connect(self._on_outline_clicked)  # Enter no item
        self.attachments_list = QListWidget()
        self.attachments_list.itemDoubleClicked.connect(self._on_attachment_activated)
        self.attachments_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attachments_list.customContextMenuRequested.connect(self._show_attachment_menu)

        self.addTab(self.thumbnail_list, "")
        self.addTab(self.outline_tree, "")
        self.addTab(self.attachments_list, "")
        self.retranslate()
        self._update_tabs()

    def setVisible(self, visible: bool) -> None:
        super().setVisible(visible)
        self.visibility_changed.emit(visible)

    def retranslate(self):
        self.setTabText(0, tr("Páginas"))
        self.setTabText(1, tr("Marcadores"))
        self.setTabText(2, tr("Anexos"))
        self.setTabToolTip(0, tr("Miniaturas (Ctrl ou Shift + clique seleciona várias)"))
        self.attachments_list.setToolTip(tr("Duplo clique abre um PDF anexado ou salva os outros arquivos"))

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
            item.setData(0, _TOP_ROLE, entry.top)
            item.setData(0, _URL_ROLE, entry.url)
            if entry.url:
                item.setToolTip(0, entry.url)
            elif entry.page_index is not None:
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
            attachment = QListWidgetItem(f"{info.name} ({_size(info.size)})")
            attachment.setData(Qt.ItemDataRole.UserRole, info.name)
            self.attachments_list.addItem(attachment)
        self._update_tabs()

    def clear(self) -> None:
        self._path = None
        self.outline_tree.clear()
        self.attachments_list.clear()
        self._update_tabs()

    def use_external_rail(self) -> None:
        """A coluna de ícones da aba de documento escolhe o conteúdo: as abas daqui somem."""
        self._external_rail = True
        self.tabBar().hide()

    def _update_tabs(self):
        self.setTabVisible(1, self.outline_tree.topLevelItemCount() > 0)
        self.setTabVisible(2, self.attachments_list.count() > 0)
        visible = sum(self.isTabVisible(index) for index in range(self.count()))
        self.tabBar().setVisible(visible > 1 and not self._external_rail)
        if not self.isTabVisible(self.currentIndex()):
            self.setCurrentIndex(0)
        self.tabs_changed.emit()

    def _on_outline_clicked(self, item: QTreeWidgetItem, _column: int):
        url = item.data(0, _URL_ROLE)
        if url:
            self.url_requested.emit(url)
            return
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            self.destination_requested.emit(int(page), item.data(0, _TOP_ROLE))

    def show_panel(self, panel: str) -> None:
        """Mostra "pages", "outline" ou "attachments", se o documento tem o que mostrar nele."""
        index = {"pages": 0, "outline": 1, "attachments": 2}[panel]
        if self.isTabVisible(index):
            self.setCurrentIndex(index)
            self.tabs_changed.emit()

    def _on_attachment_activated(self, item: QListWidgetItem):
        """Um PDF abre no próprio app. Outros tipos só são salvos: um anexo pode ser um programa,
        e rodá-lo com um duplo clique é o que um PDF não deve conseguir."""
        name = item.data(Qt.ItemDataRole.UserRole)
        if str(name).lower().endswith(".pdf"):
            self._open_attachment(name)
        else:
            self._save_attachment(name)

    def attachment_menu(self, item: QListWidgetItem) -> QMenu:
        menu = QMenu(self)
        name = item.data(Qt.ItemDataRole.UserRole)
        if str(name).lower().endswith(".pdf"):
            menu.addAction(tr("Abrir")).triggered.connect(lambda _checked=False: self._open_attachment(name))
        menu.addAction(tr("Salvar como...")).triggered.connect(lambda _checked=False: self._save_attachment(name))
        return menu

    def _show_attachment_menu(self, position):
        item = self.attachments_list.itemAt(position)
        if item is not None:
            menu = self.attachment_menu(item)
            menu.exec(self.attachments_list.viewport().mapToGlobal(position))
            menu.deleteLater()

    def _open_attachment(self, name: str):
        if not name or not self._path:
            return
        opened = self._opened_attachments.get((self._path, name))
        if opened and Path(opened).is_file():
            self.file_requested.emit(opened)
            return
        # Numa pasta própria e até o fim do app: o documento aberto continua lendo este arquivo.
        folder = tempfile.mkdtemp(prefix=ATTACHMENT_FOLDER_PREFIX)
        atexit.register(shutil.rmtree, folder, ignore_errors=True)
        target = str(Path(folder) / Path(name).name)
        try:
            SaveAttachment().run(self._path, name, target)
        except Exception as exc:
            show_error(self, tr("Abrir"), tr("Não foi possível abrir o anexo: {error}"), exc)
            return
        self._opened_attachments[(self._path, name)] = target
        self.file_requested.emit(target)

    def _save_attachment(self, name: str):
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
