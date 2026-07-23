"""Aba de marca d'água em PDFs."""

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.watermark import AddWatermark
from ui.widgets.file_picker import FilePicker


class WatermarkPage(QWidget):
    """Permite adicionar uma marca d'água de texto sobre as páginas de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Texto da marca d'água, ex: CONFIDENCIAL")

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.05, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(0.3)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(40)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 359)
        self.rotation_spin.setValue(45)

        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Opacidade:"))
        options_layout.addWidget(self.opacity_spin)
        options_layout.addWidget(QLabel("Tamanho da fonte:"))
        options_layout.addWidget(self.font_size_spin)
        options_layout.addWidget(QLabel("Rotação:"))
        options_layout.addWidget(self.rotation_spin)

        apply_button = QPushButton("Aplicar marca d'água")
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel("Texto:"))
        layout.addWidget(self.text_edit)
        layout.addLayout(options_layout)
        layout.addWidget(apply_button)

    def _apply(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()
        text = self.text_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, "Marca d'água", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Marca d'água", "Escolha o arquivo de saída.")
            return
        if not text:
            QMessageBox.warning(self, "Marca d'água", "Digite o texto da marca d'água.")
            return

        try:
            AddWatermark().run(
                input_path,
                output_path,
                text=text,
                opacity=self.opacity_spin.value(),
                font_size=self.font_size_spin.value(),
                rotation=self.rotation_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Marca d'água", f"Falha ao aplicar marca d'água: {exc}")
            return

        QMessageBox.information(self, "Marca d'água", "Marca d'água aplicada com sucesso.")
