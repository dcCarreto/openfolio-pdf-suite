"""Aba de criação de campos de formulário (AcroForm) em PDFs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from core.form_fields import AddFormField
from ui.widgets.file_picker import FilePicker

_FIELD_TYPES = {"Texto": "text", "Caixa de seleção": "checkbox"}


class FormFieldsPage(QWidget):
    """Permite adicionar campos de formulário interativos (texto ou caixa de seleção) a um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.output_picker = FilePicker(mode="save")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nome do campo, ex: nome_completo")

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(_FIELD_TYPES.keys()))

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

        self.checked_box = QCheckBox("Marcado (apenas para caixa de seleção)")

        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("Página (0 = primeira):"))
        position_layout.addWidget(self.page_spin)
        position_layout.addWidget(QLabel("X:"))
        position_layout.addWidget(self.x_spin)
        position_layout.addWidget(QLabel("Y:"))
        position_layout.addWidget(self.y_spin)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Largura:"))
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QLabel("Altura:"))
        size_layout.addWidget(self.height_spin)

        add_button = QPushButton("Adicionar campo")
        add_button.clicked.connect(self._add_field)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(QLabel("Nome do campo:"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Tipo:"))
        layout.addWidget(self.type_combo)
        layout.addLayout(position_layout)
        layout.addLayout(size_layout)
        layout.addWidget(self.checked_box)
        layout.addWidget(add_button)

    def _add_field(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()
        field_name = self.name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, "Campo de formulário", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Campo de formulário", "Escolha o arquivo de saída.")
            return
        if not field_name:
            QMessageBox.warning(self, "Campo de formulário", "Digite um nome para o campo.")
            return

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
                field_type=_FIELD_TYPES[self.type_combo.currentText()],
                checked=self.checked_box.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Campo de formulário", f"Falha ao adicionar campo: {exc}")
            return

        QMessageBox.information(self, "Campo de formulário", "Campo adicionado com sucesso.")
