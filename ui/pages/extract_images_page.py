"""Aba de extração de imagens de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.extract_images import ExtractImages
from ui.i18n import tr
from ui.widgets.file_picker import FilePicker


class ExtractImagesPage(QWidget):
    """Permite extrair as imagens embutidas nas páginas de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="directory")

        extract_button = QPushButton(tr("Extrair imagens"))
        extract_button.clicked.connect(self._extract)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel(tr("Pasta de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(extract_button)

    def _extract(self):
        input_path = self.input_picker.path()
        output_dir = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Extrair imagens"), tr("Escolha o arquivo de entrada."))
            return
        if not output_dir:
            QMessageBox.warning(self, tr("Extrair imagens"), tr("Escolha a pasta de saída."))
            return

        try:
            output_paths = ExtractImages().run(input_path, output_dir)
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Extrair imagens"),
                tr("Falha ao extrair imagens: {error}").format(error=exc),
            )
            return

        if not output_paths:
            QMessageBox.information(
                self, tr("Extrair imagens"), tr("Nenhuma imagem encontrada no PDF.")
            )
            return

        QMessageBox.information(
            self,
            tr("Extrair imagens"),
            tr("{count} imagem(ns) extraída(s) com sucesso.").format(count=len(output_paths)),
        )
