"""Aba de mesclagem de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.merge import MergePDF
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker


class MergePage(QWidget):
    """Permite escolher vários PDFs, reordená-los e mesclá-los em um único arquivo."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.file_list_editor = FileListEditor(
            dialog_caption="Selecionar PDFs", file_filter="PDF (*.pdf)"
        )
        self.output_picker = FilePicker(mode="save")

        merge_button = QPushButton("Mesclar")
        merge_button.clicked.connect(self._merge)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivos a mesclar (na ordem desejada):"))
        layout.addWidget(self.file_list_editor)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(merge_button)

    def _merge(self):
        input_paths = self.file_list_editor.paths()
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
