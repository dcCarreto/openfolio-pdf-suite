"""Aba de marca d'água em PDFs."""

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.watermark import AddWatermark
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class WatermarkPage(QWidget):
    """Permite adicionar uma marca d'água de texto sobre as páginas de um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="marca_dagua"
        )

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(tr("Texto da marca d'água, ex: CONFIDENCIAL"))

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

        options_layout = QFormLayout()
        options_layout.addRow(tr("Opacidade:"), self.opacity_spin)
        options_layout.addRow(tr("Tamanho da fonte:"), self.font_size_spin)
        options_layout.addRow(tr("Rotação:"), self.rotation_spin)

        apply_button = QPushButton(tr("Aplicar marca d'água"))
        apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Texto:")))
        layout.addWidget(self.text_edit)
        layout.addLayout(options_layout)
        layout.addWidget(apply_button)

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()
        text = self.text_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Escolha o arquivo de saída."))
            return
        if not text:
            QMessageBox.warning(self, tr("Marca d'água"), tr("Digite o texto da marca d'água."))
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
            QMessageBox.critical(
                self,
                tr("Marca d'água"),
                tr("Falha ao aplicar marca d'água: {error}").format(error=exc),
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Marca d'água"), tr("Marca d'água aplicada com sucesso."))
