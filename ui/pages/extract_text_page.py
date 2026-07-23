"""Aba de extração de texto de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.extract_text import ExtractText
from ui.widgets.file_picker import FilePicker


class ExtractTextPage(QWidget):
    """Permite extrair todo o texto de um PDF para um arquivo .txt."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save", file_filter="Texto (*.txt)")

        extract_button = QPushButton("Extrair texto")
        extract_button.clicked.connect(self._extract)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Arquivo de saída (.txt):"))
        layout.addWidget(self.output_picker)
        layout.addWidget(extract_button)

    def _extract(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Extrair texto", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Extrair texto", "Escolha o arquivo de saída.")
            return

        try:
            ExtractText().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Extrair texto", f"Falha ao extrair texto: {exc}")
            return

        QMessageBox.information(self, "Extrair texto", "Texto extraído com sucesso.")
