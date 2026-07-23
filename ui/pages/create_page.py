"""Aba de criação de novos PDFs em branco."""

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.create import CreateBlankPDF
from ui.widgets.file_picker import FilePicker


class CreatePage(QWidget):
    """Permite criar um novo PDF em branco, com uma ou mais páginas."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.output_picker = FilePicker(mode="save")

        self.page_count_spin = QSpinBox()
        self.page_count_spin.setRange(1, 999)
        self.page_count_spin.setValue(1)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 20000)
        self.width_spin.setValue(595)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 20000)
        self.height_spin.setValue(842)

        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Páginas:"))
        options_layout.addWidget(self.page_count_spin)
        options_layout.addWidget(QLabel("Largura:"))
        options_layout.addWidget(self.width_spin)
        options_layout.addWidget(QLabel("Altura:"))
        options_layout.addWidget(self.height_spin)

        create_button = QPushButton("Criar PDF")
        create_button.clicked.connect(self._create)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addLayout(options_layout)
        layout.addWidget(create_button)

    def _create(self):
        output_path = self.output_picker.path()

        if not output_path:
            QMessageBox.warning(self, "Criar PDF", "Escolha o arquivo de saída.")
            return

        try:
            CreateBlankPDF().run(
                output_path,
                page_count=self.page_count_spin.value(),
                width=self.width_spin.value(),
                height=self.height_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Criar PDF", f"Falha ao criar PDF: {exc}")
            return

        QMessageBox.information(self, "Criar PDF", "PDF criado com sucesso.")
