"""Aba de campos de formulário (AcroForm) em PDFs: criar campos, grupos de opções, listar
campos existentes, exportar/importar dados preenchidos e achatar o formulário."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.form_fields import (
    AddFormField,
    AddRadioGroup,
    ExportFormDataCSV,
    ExportFormDataFDF,
    FlattenFormFields,
    ImportFormDataCSV,
    ImportFormDataFDF,
    ListFormFields,
    RadioOption,
)
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_FIELD_TYPE_LABELS = ["Texto", "Data", "Caixa de seleção", "Lista suspensa", "Lista de seleção"]
_FIELD_TYPE_VALUES = {
    "Texto": "text",
    "Data": "date",
    "Caixa de seleção": "checkbox",
    "Lista suspensa": "dropdown",
    "Lista de seleção": "listbox",
}
_MODES = [
    "Adicionar campo",
    "Adicionar grupo de opções",
    "Listar campos",
    "Exportar dados (CSV)",
    "Exportar dados (FDF)",
    "Importar dados (CSV)",
    "Importar dados (FDF)",
    "Achatar formulário",
]


class FormFieldsPage(QWidget):
    """Permite adicionar campos de formulário interativos a um PDF, listar os já
    existentes, exportar/importar os dados preenchidos, e achatar o formulário."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr(label) for label in _MODES])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_add_field_panel())
        self.stack.addWidget(self._build_radio_group_panel())
        self.stack.addWidget(self._build_list_panel())
        self.stack.addWidget(self._build_export_panel("csv"))
        self.stack.addWidget(self._build_export_panel("fdf"))
        self.stack.addWidget(self._build_import_panel("csv"))
        self.stack.addWidget(self._build_import_panel("fdf"))
        self.stack.addWidget(self._build_flatten_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    # ---- Adicionar campo -------------------------------------------------

    def _build_add_field_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.add_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_campo"
        )

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Nome do campo, ex: nome_completo"))

        self.type_combo = QComboBox()
        self.type_combo.addItems([tr(label) for label in _FIELD_TYPE_LABELS])

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 9999)

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

        self.options_edit = QLineEdit()
        self.options_edit.setPlaceholderText(tr("Opções separadas por vírgula (ex: SP,RJ,MG)"))
        self.options_edit.setToolTip(
            tr("Aplica-se apenas aos tipos lista suspensa e lista de seleção")
        )

        position_layout = QFormLayout()
        position_layout.addRow(tr("Página:"), self.page_spin)
        position_layout.addRow("X:", self.x_spin)
        position_layout.addRow("Y:", self.y_spin)

        size_layout = QFormLayout()
        size_layout.addRow(tr("Largura:"), self.width_spin)
        size_layout.addRow(tr("Altura:"), self.height_spin)

        add_button = QPushButton(tr("Adicionar campo"))
        add_button.clicked.connect(self._add_field)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.add_output_picker)
        layout.addWidget(QLabel(tr("Nome do campo:")))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel(tr("Tipo:")))
        layout.addWidget(self.type_combo)
        layout.addLayout(position_layout)
        layout.addLayout(size_layout)
        layout.addWidget(self.checked_box)
        layout.addWidget(QLabel(tr("Opções (lista suspensa/lista de seleção):")))
        layout.addWidget(self.options_edit)
        layout.addWidget(add_button)
        return widget

    def _add_field(self):
        input_path = self.session.path()
        output_path = self.add_output_picker.path()
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
        field_type = _FIELD_TYPE_VALUES[field_label]
        options = [
            option.strip() for option in self.options_edit.text().split(",") if option.strip()
        ]

        try:
            AddFormField().run(
                input_path,
                output_path,
                field_name=field_name,
                page_number=self.page_spin.value() - 1,
                x=self.x_spin.value(),
                y=self.y_spin.value(),
                width=self.width_spin.value(),
                height=self.height_spin.value(),
                field_type=field_type,
                checked=self.checked_box.isChecked(),
                options=options or None,
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

    # ---- Adicionar grupo de opções (radio) --------------------------------

    def _build_radio_group_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.radio_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="com_grupo"
        )

        self.radio_name_edit = QLineEdit()
        self.radio_name_edit.setPlaceholderText(tr("Nome do grupo, ex: sexo"))

        self.radio_selected_edit = QLineEdit()
        self.radio_selected_edit.setPlaceholderText(tr("Valor pré-selecionado (opcional)"))

        self.radio_size_spin = QDoubleSpinBox()
        self.radio_size_spin.setRange(4, 64)
        self.radio_size_spin.setValue(16)

        self.radio_table = QTableWidget(0, 4)
        self.radio_table.setHorizontalHeaderLabels(
            [tr("Valor"), tr("Página"), "X", "Y"]
        )

        add_row_button = QPushButton(tr("Adicionar opção"))
        add_row_button.clicked.connect(self._add_radio_row)
        remove_row_button = QPushButton(tr("Remover opção"))
        remove_row_button.clicked.connect(self._remove_radio_row)

        row_buttons_layout = QHBoxLayout()
        row_buttons_layout.addWidget(add_row_button)
        row_buttons_layout.addWidget(remove_row_button)

        create_button = QPushButton(tr("Criar grupo"))
        create_button.clicked.connect(self._add_radio_group)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.radio_output_picker)
        layout.addWidget(QLabel(tr("Nome do campo:")))
        layout.addWidget(self.radio_name_edit)
        layout.addWidget(self.radio_table)
        layout.addLayout(row_buttons_layout)
        layout.addWidget(QLabel(tr("Tamanho:")))
        layout.addWidget(self.radio_size_spin)
        layout.addWidget(self.radio_selected_edit)
        layout.addWidget(create_button)
        self._add_radio_row()
        self._add_radio_row()
        return widget

    def _add_radio_row(self):
        row = self.radio_table.rowCount()
        self.radio_table.insertRow(row)
        self.radio_table.setItem(row, 0, QTableWidgetItem(""))
        self.radio_table.setItem(row, 1, QTableWidgetItem("1"))
        self.radio_table.setItem(row, 2, QTableWidgetItem("0"))
        self.radio_table.setItem(row, 3, QTableWidgetItem("0"))

    def _remove_radio_row(self):
        row = self.radio_table.currentRow()
        if row >= 0:
            self.radio_table.removeRow(row)

    def _add_radio_group(self):
        input_path = self.session.path()
        output_path = self.radio_output_picker.path()
        field_name = self.radio_name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Grupo de opções"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Grupo de opções"), tr("Escolha o arquivo de saída."))
            return
        if not field_name:
            QMessageBox.warning(self, tr("Grupo de opções"), tr("Digite um nome para o campo."))
            return

        try:
            options = []
            for row in range(self.radio_table.rowCount()):
                value = self.radio_table.item(row, 0).text().strip()
                if not value:
                    continue
                page_number = int(self.radio_table.item(row, 1).text()) - 1
                x = float(self.radio_table.item(row, 2).text())
                y = float(self.radio_table.item(row, 3).text())
                options.append(RadioOption(value=value, page_number=page_number, x=x, y=y))
        except ValueError:
            QMessageBox.warning(
                self,
                tr("Grupo de opções"),
                tr("Página, X e Y precisam ser números em todas as linhas preenchidas."),
            )
            return

        selected_value = self.radio_selected_edit.text().strip() or None

        try:
            AddRadioGroup().run(
                input_path,
                output_path,
                field_name=field_name,
                options=options,
                size=self.radio_size_spin.value(),
                selected_value=selected_value,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Grupo de opções"), tr("Falha ao criar grupo: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Grupo de opções"), tr("Grupo criado com sucesso."))

    # ---- Listar campos -----------------------------------------------------

    def _build_list_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar campos"))
        list_button.clicked.connect(self._list_fields)

        self.fields_list = QListWidget()

        layout.addWidget(list_button)
        layout.addWidget(self.fields_list)
        return widget

    def _list_fields(self):
        input_path = self.session.path()
        self.fields_list.clear()
        if not input_path:
            QMessageBox.warning(self, tr("Campos de formulário"), tr("Abra um PDF para começar."))
            return

        try:
            fields = ListFormFields().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Campos de formulário"),
                tr("Falha ao listar campos: {error}").format(error=exc),
            )
            return

        if not fields:
            self.fields_list.addItem(tr("Nenhum campo de formulário encontrado."))
            return

        for field in fields:
            self.fields_list.addItem(f"{field.name} — {field.field_type} — {field.value}")

    # ---- Exportar dados -----------------------------------------------------

    def _build_export_panel(self, fmt: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        file_filter = "CSV (*.csv)" if fmt == "csv" else "FDF (*.fdf)"
        output_picker = FilePicker(mode="save", file_filter=file_filter)

        export_button = QPushButton(tr("Exportar"))
        export_button.clicked.connect(lambda: self._export_data(fmt, output_picker))

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(output_picker)
        layout.addWidget(export_button)
        return widget

    def _export_data(self, fmt: str, output_picker: FilePicker):
        input_path = self.session.path()
        output_path = output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Exportar dados"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Exportar dados"), tr("Escolha o arquivo de saída."))
            return

        operation = ExportFormDataCSV() if fmt == "csv" else ExportFormDataFDF()
        try:
            count = operation.run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Exportar dados"), tr("Falha ao exportar dados: {error}").format(error=exc)
            )
            return

        QMessageBox.information(
            self, tr("Exportar dados"), tr("{count} campo(s) exportado(s) com sucesso.").format(count=count)
        )

    # ---- Importar dados -----------------------------------------------------

    def _build_import_panel(self, fmt: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        file_filter = "CSV (*.csv)" if fmt == "csv" else "FDF (*.fdf)"
        data_picker = FilePicker(mode="open", file_filter=file_filter)
        output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="preenchido"
        )

        import_button = QPushButton(tr("Importar"))
        import_button.clicked.connect(lambda: self._import_data(fmt, data_picker, output_picker))

        label = tr("Arquivo CSV com os dados:") if fmt == "csv" else tr("Arquivo FDF com os dados:")
        layout.addWidget(QLabel(label))
        layout.addWidget(data_picker)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(output_picker)
        layout.addWidget(import_button)
        return widget

    def _import_data(self, fmt: str, data_picker: FilePicker, output_picker: FilePicker):
        input_path = self.session.path()
        data_path = data_picker.path()
        output_path = output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Importar dados"), tr("Abra um PDF para começar."))
            return
        if not data_path:
            QMessageBox.warning(self, tr("Importar dados"), tr("Escolha o arquivo de dados."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Importar dados"), tr("Escolha o arquivo de saída."))
            return

        operation = ImportFormDataCSV() if fmt == "csv" else ImportFormDataFDF()
        try:
            result = operation.run(input_path, output_path, data_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Importar dados"), tr("Falha ao importar dados: {error}").format(error=exc)
            )
            return

        self.session.open(output_path)
        message = tr("{count} campo(s) preenchido(s) com sucesso.").format(count=result.filled)
        if result.not_found:
            message += "\n\n" + tr("Sem campo correspondente no PDF (ignorados): {names}").format(
                names=", ".join(result.not_found)
            )
        QMessageBox.information(self, tr("Importar dados"), message)

    # ---- Achatar formulário --------------------------------------------------

    def _build_flatten_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Grava o valor atual de cada campo preenchido como conteúdo estático da "
                "página e remove os widgets interativos. Campos sem valor definido são "
                "deixados como estão."
            )
        )
        note.setWordWrap(True)

        self.flatten_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="achatado"
        )
        flatten_button = QPushButton(tr("Achatar formulário"))
        flatten_button.clicked.connect(self._flatten_form)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.flatten_output_picker)
        layout.addWidget(flatten_button)
        return widget

    def _flatten_form(self):
        input_path = self.session.path()
        output_path = self.flatten_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Achatar formulário"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Achatar formulário"), tr("Escolha o arquivo de saída."))
            return

        try:
            count = FlattenFormFields().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("Achatar formulário"),
                tr("Falha ao achatar formulário: {error}").format(error=exc),
            )
            return

        self.session.open(output_path)
        QMessageBox.information(
            self,
            tr("Achatar formulário"),
            tr("{count} campo(s) achatado(s) com sucesso.").format(count=count),
        )
