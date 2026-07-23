"""Aba de mesclagem de PDFs."""

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.merge import MergePDF
from ui.widgets.file_picker import FilePicker


class MergePage(QWidget):
    """Permite escolher vários PDFs, reordená-los e mesclá-los em um único arquivo."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.file_list = QListWidget()

        add_button = QPushButton("Adicionar arquivos...")
        add_button.clicked.connect(self._add_files)
        remove_button = QPushButton("Remover selecionado")
        remove_button.clicked.connect(self._remove_selected)
        up_button = QPushButton("Subir")
        up_button.clicked.connect(lambda: self._move_selected(-1))
        down_button = QPushButton("Descer")
        down_button.clicked.connect(lambda: self._move_selected(1))

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addWidget(up_button)
        buttons_layout.addWidget(down_button)

        self.output_picker = FilePicker(mode="save")

        merge_button = QPushButton("Mesclar")
        merge_button.clicked.connect(self._merge)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivos a mesclar (na ordem desejada):"))
        layout.addWidget(self.file_list)
        layout.addLayout(buttons_layout)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(merge_button)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Selecionar PDFs", "", "PDF (*.pdf)")
        for path in paths:
            self.file_list.addItem(path)

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _move_selected(self, offset: int):
        row = self.file_list.currentRow()
        new_row = row + offset
        if row < 0 or not (0 <= new_row < self.file_list.count()):
            return
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(new_row, item)
        self.file_list.setCurrentRow(new_row)

    def _merge(self):
        input_paths = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        output_path = self.output_picker.path()

        if not input_paths:
            QMessageBox.warning(self, "Mesclar", "Adicione pelo menos um arquivo.")
            return
        if not output_path:
            QMessageBox.warning(self, "Mesclar", "Escolha o arquivo de saída.")
            return

        try:
            MergePDF().run(input_paths, output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Mesclar", f"Falha ao mesclar: {exc}")
            return

        QMessageBox.information(self, "Mesclar", "PDFs mesclados com sucesso.")
