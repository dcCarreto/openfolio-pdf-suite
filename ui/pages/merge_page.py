"""Aba de mesclagem de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.merge import MergePDF
from ui.i18n import tr
from ui.widgets.file_list_editor import FileListEditor
from ui.widgets.file_picker import FilePicker


class MergePage(QWidget):
    """Permite escolher vários PDFs, reordená-los e mesclá-los em um único arquivo."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.file_list_editor = FileListEditor(
            dialog_caption=tr("Selecionar PDFs"), file_filter="PDF (*.pdf)"
        )
        self.output_picker = FilePicker(mode="save")

        merge_button = QPushButton(tr("Mesclar"))
        merge_button.clicked.connect(self._merge)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivos a mesclar (na ordem desejada):")))
        layout.addWidget(self.file_list_editor)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(merge_button)

    def _merge(self):
        input_paths = self.file_list_editor.paths()
        output_path = self.output_picker.path()

        if not input_paths:
            QMessageBox.warning(self, tr("Mesclar"), tr("Adicione pelo menos um arquivo."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Mesclar"), tr("Escolha o arquivo de saída."))
            return

        try:
            MergePDF().run(input_paths, output_path)
        except Exception as exc:
            QMessageBox.critical(self, tr("Mesclar"), tr("Falha ao mesclar: {error}").format(error=exc))
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Mesclar"), tr("PDFs mesclados com sucesso."))
