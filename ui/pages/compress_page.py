"""Aba de compressão de PDFs."""

from pathlib import Path

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.compress import CompressPDF
from ui.i18n import tr
from ui.widgets.file_picker import FilePicker


class CompressPage(QWidget):
    """Permite reduzir o tamanho de um arquivo PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        compress_button = QPushButton(tr("Comprimir"))
        compress_button.clicked.connect(self._compress)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(compress_button)

    def _compress(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Comprimir"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Comprimir"), tr("Escolha o arquivo de saída."))
            return

        try:
            CompressPDF().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Comprimir"), tr("Falha ao comprimir: {error}").format(error=exc)
            )
            return

        original_size = Path(input_path).stat().st_size
        compressed_size = Path(output_path).stat().st_size
        reduction = 100 * (1 - compressed_size / original_size) if original_size else 0
        QMessageBox.information(
            self,
            tr("Comprimir"),
            tr("PDF comprimido: {original} KB -> {compressed} KB ({reduction}% menor).").format(
                original=f"{original_size / 1024:.1f}",
                compressed=f"{compressed_size / 1024:.1f}",
                reduction=f"{reduction:.0f}",
            ),
        )
