"""Aba de criação de campos de formulário (AcroForm) em PDFs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from core.form_fields import AddFormField
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_FIELD_TYPE_LABELS = ["Texto", "Caixa de seleção"]
_FIELD_TYPE_VALUES = {"Texto": "text", "Caixa de seleção": "checkbox"}


class FormFieldsPage(QWidget):
    """Permite adicionar campos de formulário interativos (texto ou caixa de seleção) a um PDF."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)
        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="com_campo"
        )

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Nome do campo, ex: nome_completo"))

        self.type_combo = QComboBox()
        self.type_combo.addItems([tr(label) for label in _FIELD_TYPE_LABELS])

        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 9999)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0, 20000)
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0, 20000)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 2000)
        self.width_spin.setValue(200)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 2000)
        self.height_spin.setValue(20)

        self.checked_box = QCheckBox(tr("Marcado"))
        self.checked_box.setToolTip(tr("Aplica-se apenas ao tipo caixa de seleção"))

        position_layout = QFormLayout()
        position_layout.addRow(tr("Página (0 = primeira):"), self.page_spin)
        position_layout.addRow("X:", self.x_spin)
        position_layout.addRow("Y:", self.y_spin)

        size_layout = QFormLayout()
        size_layout.addRow(tr("Largura:"), self.width_spin)
        size_layout.addRow(tr("Altura:"), self.height_spin)

        add_button = QPushButton(tr("Adicionar campo"))
        add_button.clicked.connect(self._add_field)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel(tr("Nome do campo:")))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel(tr("Tipo:")))
        layout.addWidget(self.type_combo)
        layout.addLayout(position_layout)
        layout.addLayout(size_layout)
        layout.addWidget(self.checked_box)
        layout.addWidget(add_button)

    def _add_field(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()
        field_name = self.name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Campo de formulário"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Campo de formulário"), tr("Escolha o arquivo de saída."))
            return
        if not field_name:
            QMessageBox.warning(
                self, tr("Campo de formulário"), tr("Digite um nome para o campo.")
            )
            return

        field_label = _FIELD_TYPE_LABELS[self.type_combo.currentIndex()]

        try:
            AddFormField().run(
                input_path,
                output_path,
                field_name=field_name,
                page_number=self.page_spin.value(),
                x=self.x_spin.value(),
                y=self.y_spin.value(),
                width=self.width_spin.value(),
                height=self.height_spin.value(),
                field_type=_FIELD_TYPE_VALUES[field_label],
                checked=self.checked_box.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Campo de formulário"),
                tr("Falha ao adicionar campo: {error}").format(error=exc),
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Campo de formulário"), tr("Campo adicionado com sucesso."))
