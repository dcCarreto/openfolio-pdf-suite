"""Widget reutilizável: lista de arquivos que o usuário pode adicionar, remover e reordenar.

Arquivos arrastados do explorador para a lista entram nela (só os do tipo aceito pelo filtro).
"""

import re
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder


class FileListEditor(QWidget):
    """Lista de arquivos com botões de adicionar, remover e mover (subir/descer)."""

    def __init__(self, dialog_caption: str, file_filter: str, parent=None):
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

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self._dialog_caption, start_folder(), self._file_filter)
        if paths:
            remember_folder_of(paths[0])
        for path in paths:
            self.list_widget.addItem(path)

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
            self.list_widget.addItem(path)
        if paths:
            event.acceptProposedAction()

    def paths(self) -> list[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
