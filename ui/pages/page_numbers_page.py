"""Aba de numeração de páginas de PDFs."""

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.page_numbers import AddPageNumbers
from ui.widgets.file_picker import FilePicker


class PageNumbersPage(QWidget):
    """Permite adicionar números de página no rodapé de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        self.start_at_spin = QSpinBox()
        self.start_at_spin.setRange(0, 9999)
        self.start_at_spin.setValue(1)

        apply_button = QPushButton("Adicionar numeração")
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel("Começar em:"))
        layout.addWidget(self.start_at_spin)
        layout.addWidget(apply_button)

    def _apply(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Numeração de páginas", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Numeração de páginas", "Escolha o arquivo de saída.")
            return

        try:
            AddPageNumbers().run(input_path, output_path, start_at=self.start_at_spin.value())
        except Exception as exc:
            QMessageBox.critical(self, "Numeração de páginas", f"Falha ao numerar páginas: {exc}")
            return

        QMessageBox.information(self, "Numeração de páginas", "Numeração adicionada com sucesso.")
