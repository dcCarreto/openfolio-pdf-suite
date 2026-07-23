"""Widget reutilizável: lista de arquivos que o usuário pode adicionar, remover e reordenar."""

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FileListEditor(QWidget):
    """Lista de arquivos com botões de adicionar, remover e mover (subir/descer)."""

    def __init__(self, dialog_caption: str, file_filter: str, parent=None):
        super().__init__(parent)
        self._dialog_caption = dialog_caption
        self._file_filter = file_filter

        self.list_widget = QListWidget()

        add_button = QPushButton("Adicionar...")
        add_button.setToolTip("Adicionar arquivos à lista")
        add_button.clicked.connect(self._add)
        remove_button = QPushButton("Remover selecionado")
        remove_button.setToolTip("Remover o item selecionado da lista")
        remove_button.clicked.connect(self._remove_selected)
        up_button = QPushButton("Subir")
        up_button.setToolTip("Mover o item selecionado para cima")
        up_button.clicked.connect(lambda: self._move_selected(-1))
        down_button = QPushButton("Descer")
        down_button.setToolTip("Mover o item selecionado para baixo")
        down_button.clicked.connect(lambda: self._move_selected(1))

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addWidget(up_button)
        buttons_layout.addWidget(down_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)
        layout.addLayout(buttons_layout)

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self._dialog_caption, "", self._file_filter)
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

    def paths(self) -> list[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
