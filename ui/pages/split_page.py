"""Aba de divisão de PDFs."""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.split import SplitPDF
from ui.widgets.file_picker import FilePicker


class SplitPage(QWidget):
    """Permite dividir um PDF em múltiplos arquivos, N páginas por vez."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="directory")

        self.pages_per_file_spin = QSpinBox()
        self.pages_per_file_spin.setMinimum(1)
        self.pages_per_file_spin.setValue(1)

        split_button = QPushButton("Dividir")
        split_button.clicked.connect(self._split)

        pages_layout = QHBoxLayout()
        pages_layout.addWidget(QLabel("Páginas por arquivo:"))
        pages_layout.addWidget(self.pages_per_file_spin)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Pasta de saída:"))
        layout.addWidget(self.output_picker)
        layout.addLayout(pages_layout)
        layout.addWidget(split_button)

    def _split(self):
        input_path = self.input_picker.path()
        output_dir = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Dividir", "Escolha o arquivo de entrada.")
            return
        if not output_dir:
            QMessageBox.warning(self, "Dividir", "Escolha a pasta de saída.")
            return

        try:
            output_paths = SplitPDF().run(
                input_path, output_dir, pages_per_file=self.pages_per_file_spin.value()
            )
        except Exception as exc:
            QMessageBox.critical(self, "Dividir", f"Falha ao dividir: {exc}")
            return

        QMessageBox.information(self, "Dividir", f"PDF dividido em {len(output_paths)} arquivo(s).")
