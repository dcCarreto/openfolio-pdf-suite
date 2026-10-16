"""Aba de compressão de PDFs."""

from pathlib import Path

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.compress import CompressPDF
from ui.i18n import tr
from ui.tasks import call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class CompressPage(QWidget):
    """Permite reduzir o tamanho de um arquivo PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="comprimido"
        )

        compress_button = QPushButton(tr("Comprimir"))
        compress_button.clicked.connect(self._compress)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(compress_button)

    def _compress(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Comprimir"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Comprimir"), tr("Escolha o arquivo de saída."))
            return

        task = call_with_progress(CompressPDF().run, input_path, output_path)

        def done(_result):
            original_size = Path(input_path).stat().st_size
            compressed_size = Path(output_path).stat().st_size
            reduction = 100 * (1 - compressed_size / original_size) if original_size else 0
            self.session.open(output_path)
            QMessageBox.information(
                self,
                tr("Comprimir"),
                tr("PDF comprimido: {original} KB -> {compressed} KB ({reduction}% menor).").format(
                    original=f"{original_size / 1024:.1f}",
                    compressed=f"{compressed_size / 1024:.1f}",
                    reduction=f"{reduction:.0f}",
                ),
            )

        run_task(
            self,
            tr("Comprimir"),
            task,
            on_success=done,
            error_message=tr("Falha ao comprimir: {error}"),
        )
