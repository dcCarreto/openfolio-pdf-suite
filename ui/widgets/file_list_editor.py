"""Widget reutilizável: lista de arquivos que o usuário pode adicionar, remover e reordenar.

Arquivos arrastados do explorador para a lista entram nela (só os do tipo aceito pelo filtro).
Com `with_pages`, cada arquivo tem também as páginas escolhidas ("1-3, 5"; vazio = todas).
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder


class FileListEditor(QWidget):
    """Lista de arquivos com botões de adicionar, remover e mover (subir/descer)."""

    def __init__(self, dialog_caption: str, file_filter: str, parent=None, with_pages: bool = False):
        super().__init__(parent)
        self._dialog_caption = dialog_caption
        self._file_filter = file_filter
        self._extensions = {ext.lower() for ext in re.findall(r"\*(\.\w+)", file_filter)}
        self.setAcceptDrops(True)

        self.list_widget = QListWidget()

        add_button = QPushButton(tr("Adicionar..."))
        add_button.setToolTip(tr("Adicionar arquivos à lista"))
        add_button.clicked.connect(self._add)
        remove_button = QPushButton(tr("Remover selecionado"))
        remove_button.setToolTip(tr("Remover o item selecionado da lista"))
        remove_button.clicked.connect(self._remove_selected)
        up_button = QPushButton(tr("Subir"))
        up_button.setToolTip(tr("Mover o item selecionado para cima"))
        up_button.clicked.connect(lambda: self._move_selected(-1))
        down_button = QPushButton(tr("Descer"))
        down_button.setToolTip(tr("Mover o item selecionado para baixo"))
        down_button.clicked.connect(lambda: self._move_selected(1))

        buttons_row_1 = QHBoxLayout()
        buttons_row_1.addWidget(add_button)
        buttons_row_1.addWidget(remove_button)

        buttons_row_2 = QHBoxLayout()
        buttons_row_2.addWidget(up_button)
        buttons_row_2.addWidget(down_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)
        layout.addLayout(buttons_row_1)
        layout.addLayout(buttons_row_2)

        self.pages_edit: QLineEdit | None = None
        if with_pages:
            self.pages_edit = QLineEdit()
            self.pages_edit.setPlaceholderText(tr("todas (ex.: 1-3, 5)"))
            self.pages_edit.setEnabled(False)
            self.pages_edit.textEdited.connect(self._set_selected_pages)
            self.list_widget.currentItemChanged.connect(self._show_selected_pages)
            pages_row = QHBoxLayout()
            pages_row.addWidget(QLabel(tr("Páginas do arquivo selecionado:")))
            pages_row.addWidget(self.pages_edit)
            layout.addLayout(pages_row)

    # O item guarda [caminho, páginas] (o widget_state preserva o UserRole na troca de idioma);
    # o texto mostra as páginas entre colchetes, sem palavras que dependam do idioma.
    def add_path(self, path: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, [path, ""])
        item.setText(path)
        self.list_widget.addItem(item)

    def _show_selected_pages(self, item, _previous=None) -> None:
        assert self.pages_edit is not None
        self.pages_edit.setEnabled(item is not None)
        self.pages_edit.setText(item.data(Qt.ItemDataRole.UserRole)[1] if item is not None else "")

    def _set_selected_pages(self, text: str) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)[0]
        item.setData(Qt.ItemDataRole.UserRole, [path, text.strip()])
        item.setText(f"{path}  [{text.strip()}]" if text.strip() else path)

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self._dialog_caption, start_folder(), self._file_filter)
        if paths:
            remember_folder_of(paths[0])
        for path in paths:
            self.add_path(path)

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _move_selected(self, offset: int):
        row = self.list_widget.currentRow()
        new_row = row + offset
        if row < 0 or not (0 <= new_row < self.list_widget.count()):
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(new_row, item)
        self.list_widget.setCurrentRow(new_row)

    def _dropped_paths(self, mime_data) -> list[str]:
        if mime_data is None or not mime_data.hasUrls():
            return []
        paths = [str(Path(url.toLocalFile())) for url in mime_data.urls() if url.isLocalFile()]
        return [path for path in paths if Path(path).is_file() and Path(path).suffix.lower() in self._extensions]

    def dragEnterEvent(self, event):
        if self._dropped_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self._dropped_paths(event.mimeData())
        for path in paths:
            self.add_path(path)
        if paths:
            event.acceptProposedAction()

    def entries(self) -> list[tuple[str, str]]:
        """(caminho, páginas digitadas) de cada arquivo, na ordem da lista."""
        return [tuple(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.list_widget.count())]

    def paths(self) -> list[str]:
        return [path for path, _pages in self.entries()]
