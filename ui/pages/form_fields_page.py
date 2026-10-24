"""Aba de campos de formulário (AcroForm) em PDFs: criar campos, grupos de opções, editar,
remover e ordenar os campos existentes, exportar/importar dados preenchidos e achatar o
formulário."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
    EditFormField,
    ExportFormDataCSV,
    ExportFormDataFDF,
    FormFieldInfo,
    FlattenFormFields,
    ImportFormDataCSV,
    ImportFormDataFDF,
    ListFormFields,
    RadioOption,
    RemoveFormField,
    SetTabOrder,
)
from ui.area_pick_state import AreaPickState
from ui.i18n import tr
from ui.tasks import call, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success

_FIELD_TYPE_LABELS = ["Texto", "Data", "Caixa de seleção", "Lista suspensa", "Lista de seleção"]
_FIELD_TYPE_VALUES = {
    "Texto": "text",
    "Data": "date",
    "Caixa de seleção": "checkbox",
    "Lista suspensa": "dropdown",
    "Lista de seleção": "listbox",
}
_TAB_ORDERS = [
    ("A ordem da lista (arraste para mudar)", "list"),
    ("Por linhas", "rows"),
    ("Por colunas", "columns"),
]
_ADD_FIELD_MODE = 0
_RADIO_MODE = 1
_MODES = [
    "Adicionar campo",
    "Adicionar grupo de opções",
    "Editar campos existentes",
    "Exportar dados (CSV ou Excel)",
    "Exportar dados (FDF)",
    "Importar dados (CSV ou Excel)",
    "Importar dados (FDF)",
    "Achatar formulário",
]


class FormFieldsPage(QWidget):
    """Permite adicionar campos de formulário interativos a um PDF, listar os já
    existentes, exportar/importar os dados preenchidos, e achatar o formulário."""

    def __init__(self, session, area_pick_state: AreaPickState | None = None, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.area_pick_state = area_pick_state or AreaPickState()
        self.area_pick_state.area_picked.connect(self._on_area_picked)

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
        self._on_mode_changed(self.mode_combo.currentIndex())

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        self.area_pick_state.set_wanted(self, index in (_ADD_FIELD_MODE, _RADIO_MODE))
        self._publish_areas()

    # ---- Posição pelo visualizador -----------------------------------------

    def _on_area_picked(self, page_index: int, left: float, bottom: float, right: float, top: float):
        if self.area_pick_state.owner() is not self:
            return
        if self.mode_combo.currentIndex() == _ADD_FIELD_MODE:
            self.page_spin.setValue(page_index + 1)
            self.x_spin.setValue(left)
            self.y_spin.setValue(bottom)
            self.width_spin.setValue(max(1.0, right - left))
            self.height_spin.setValue(max(1.0, top - bottom))
        else:
            # Grupo de opções: a área marca a opção selecionada (ou a próxima sem posição).
            row = self.radio_table.currentRow()
            if row < 0:
                row = next(
                    (r for r in range(self.radio_table.rowCount()) if self.radio_table.item(r, 2).text() in ("", "0")),
                    -1,
                )
            if row < 0:
                self._add_radio_row()
                row = self.radio_table.rowCount() - 1
            for column, value in ((1, str(page_index + 1)), (2, f"{left:.1f}"), (3, f"{bottom:.1f}")):
                self.radio_table.item(row, column).setText(value)
            if row + 1 < self.radio_table.rowCount():
                self.radio_table.setCurrentCell(row + 1, 0)
        self._publish_areas()

    def _publish_areas(self):
        if not hasattr(self, "radio_table"):
            return  # ainda construindo os painéis
        if self.mode_combo.currentIndex() == _ADD_FIELD_MODE:
            left, bottom = self.x_spin.value(), self.y_spin.value()
            rect = (left, bottom, left + self.width_spin.value(), bottom + self.height_spin.value())
            self.area_pick_state.set_areas(self, [(self.page_spin.value() - 1, rect)], 0)
            return
        size = self.radio_size_spin.value()
        areas = []
        for row in range(self.radio_table.rowCount()):
            try:
                page = int(self.radio_table.item(row, 1).text()) - 1
                x, y = float(self.radio_table.item(row, 2).text()), float(self.radio_table.item(row, 3).text())
            except (AttributeError, ValueError):
                areas.append((-1, (0.0, 0.0, 0.0, 0.0)))
                continue
            areas.append((page, (x, y, x + size, y + size)))
        current = self.radio_table.currentRow()
        self.area_pick_state.set_areas(self, areas, current if current >= 0 else None)

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

        self.date_mask_box = QCheckBox(tr("Aceitar só datas (usa JavaScript)"))
        self.date_mask_box.setToolTip(
            tr(
                "Os leitores com JavaScript (como o Acrobat) recusam o que não for uma data DD/MM/AAAA. "
                "Fica desligado porque põe JavaScript no PDF; sem ele, o campo tem só a dica do formato."
            )
        )
        self.type_combo.currentIndexChanged.connect(self._update_date_mask_state)
        self._update_date_mask_state()

        self.options_edit = QLineEdit()
        self.options_edit.setPlaceholderText(tr("Opções separadas por vírgula (ex: SP,RJ,MG)"))
        self.options_edit.setToolTip(
            tr("Aplica-se apenas aos tipos lista suspensa e lista de seleção")
        )

        for spin in (self.page_spin, self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._publish_areas)
        position_hint = QLabel(tr("Arraste no visualizador para marcar onde o campo fica, ou ajuste os valores (pontos PDF)."))
        position_hint.setWordWrap(True)

        position_layout = QFormLayout()
        position_layout.addRow(tr("Página:"), self.page_spin)
        position_layout.addRow("X:", self.x_spin)
        position_layout.addRow("Y:", self.y_spin)

        size_layout = QFormLayout()
        size_layout.addRow(tr("Largura:"), self.width_spin)
        size_layout.addRow(tr("Altura:"), self.height_spin)

        add_button = QPushButton(tr("Adicionar campo"))
        self.action_buttons.append(add_button)
        add_button.clicked.connect(self._add_field)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.add_output_picker)
        layout.addWidget(QLabel(tr("Nome do campo:")))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel(tr("Tipo:")))
        layout.addWidget(self.type_combo)
        layout.addWidget(position_hint)
        layout.addLayout(position_layout)
        layout.addLayout(size_layout)
        layout.addWidget(self.checked_box)
        layout.addWidget(self.date_mask_box)
        layout.addWidget(QLabel(tr("Opções (lista suspensa/lista de seleção):")))
        layout.addWidget(self.options_edit)
        layout.addWidget(add_button)
        return widget

    def _update_date_mask_state(self):
        is_date = _FIELD_TYPE_VALUES[_FIELD_TYPE_LABELS[self.type_combo.currentIndex()]] == "date"
        self.date_mask_box.setEnabled(is_date)

    def _add_field(self):
        input_path = self.session.path()
        output_path = self.add_output_picker.path()
        field_name = self.name_edit.text().strip()

        if not input_path:
            notify_error(self, tr("Campo de formulário"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Campo de formulário"), tr("Escolha o arquivo de saída."))
            return
        if not field_name:
            notify_error(
                self, tr("Campo de formulário"), tr("Digite um nome para o campo.")
            )
            return

        field_label = _FIELD_TYPE_LABELS[self.type_combo.currentIndex()]
        field_type = _FIELD_TYPE_VALUES[field_label]
        options = [
            option.strip() for option in self.options_edit.text().split(",") if option.strip()
        ]

        task = call(
            AddFormField().run,
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
            date_mask=field_type == "date" and self.date_mask_box.isChecked(),
        )

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Campo de formulário"), tr("Campo adicionado com sucesso."))

        run_task(
            self,
            tr("Campo de formulário"),
            task,
            on_success=done,
            error_message=tr("Falha ao adicionar campo: {error}"),
        )

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
        self.radio_table.itemChanged.connect(lambda _item: self._publish_areas())
        self.radio_table.currentCellChanged.connect(lambda *_args: self._publish_areas())
        self.radio_size_spin.valueChanged.connect(self._publish_areas)
        radio_hint = QLabel(tr("Selecione uma opção na tabela e arraste no visualizador para marcar onde ela fica."))
        radio_hint.setWordWrap(True)

        add_row_button = QPushButton(tr("Adicionar opção"))
        add_row_button.clicked.connect(self._add_radio_row)
        remove_row_button = QPushButton(tr("Remover opção"))
        remove_row_button.clicked.connect(self._remove_radio_row)

        row_buttons_layout = QHBoxLayout()
        row_buttons_layout.addWidget(add_row_button)
        row_buttons_layout.addWidget(remove_row_button)

        create_button = QPushButton(tr("Criar grupo"))
        self.action_buttons.append(create_button)
        create_button.clicked.connect(self._add_radio_group)

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.radio_output_picker)
        layout.addWidget(QLabel(tr("Nome do campo:")))
        layout.addWidget(self.radio_name_edit)
        layout.addWidget(radio_hint)
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
            notify_error(self, tr("Grupo de opções"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Grupo de opções"), tr("Escolha o arquivo de saída."))
            return
        if not field_name:
            notify_error(self, tr("Grupo de opções"), tr("Digite um nome para o campo."))
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
            notify_error(
                self,
                tr("Grupo de opções"),
                tr("Página, X e Y precisam ser números em todas as linhas preenchidas."),
            )
            return

        selected_value = self.radio_selected_edit.text().strip() or None

        task = call(
            AddRadioGroup().run,
            input_path,
            output_path,
            field_name=field_name,
            options=options,
            size=self.radio_size_spin.value(),
            selected_value=selected_value,
        )

        def done(_result):
            self.session.open(output_path)
            notify_success(self, tr("Grupo de opções"), tr("Grupo criado com sucesso."))

        run_task(
            self,
            tr("Grupo de opções"),
            task,
            on_success=done,
            error_message=tr("Falha ao criar grupo: {error}"),
        )

    # ---- Editar campos existentes --------------------------------------------

    def _build_list_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        list_button = QPushButton(tr("Listar campos"))
        self.action_buttons.append(list_button)
        list_button.clicked.connect(self._list_fields)

        self.fields_list = QListWidget()
        self.fields_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.fields_list.setToolTip(tr("Na ordem de tabulação: arraste para mudar a ordem."))
        self.fields_list.currentItemChanged.connect(self._show_field)
        self._field_infos: dict[str, FormFieldInfo] = {}

        self.edit_name_edit = QLineEdit()
        self.edit_tooltip_edit = QLineEdit()
        self.edit_tooltip_edit.setPlaceholderText(tr("Texto que aparece ao passar o mouse (opcional)"))
        self.edit_read_only_box = QCheckBox(tr("Somente leitura"))
        self.edit_required_box = QCheckBox(tr("Obrigatório"))
        edit_form = QFormLayout()
        edit_form.addRow(tr("Nome:"), self.edit_name_edit)
        edit_form.addRow(tr("Dica:"), self.edit_tooltip_edit)
        flags_row = QHBoxLayout()
        flags_row.addWidget(self.edit_read_only_box)
        flags_row.addWidget(self.edit_required_box)
        edit_form.addRow("", flags_row)

        apply_button = QPushButton(tr("Aplicar ao campo"))
        apply_button.clicked.connect(self._apply_field_edit)
        remove_button = QPushButton(tr("Remover campo"))
        remove_button.clicked.connect(self._remove_field)
        field_buttons = QHBoxLayout()
        field_buttons.addWidget(apply_button)
        field_buttons.addWidget(remove_button)

        self.tab_order_combo = QComboBox()
        for label, value in _TAB_ORDERS:
            self.tab_order_combo.addItem(tr(label), value)
        tab_button = QPushButton(tr("Gravar ordem"))  # o rótulo "Ordem de tabulação:" fica logo acima
        tab_button.clicked.connect(self._apply_tab_order)
        tab_row = QHBoxLayout()
        tab_row.addWidget(self.tab_order_combo, 1)
        tab_row.addWidget(tab_button)

        self.edit_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="formulario"
        )

        layout.addWidget(list_button)
        layout.addWidget(self.fields_list)
        layout.addWidget(QLabel(tr("Campo selecionado:")))
        layout.addLayout(edit_form)
        layout.addLayout(field_buttons)
        layout.addWidget(QLabel(tr("Ordem de tabulação:")))
        layout.addLayout(tab_row)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.edit_output_picker)
        return widget

    def _list_fields(self):
        input_path = self.session.path()
        self.fields_list.clear()
        self._field_infos = {}
        if not input_path:
            notify_error(self, tr("Campos de formulário"), tr("Abra um PDF para começar."))
            return

        task = call(ListFormFields().run, input_path)

        def done(fields):
            self.fields_list.clear()
            if not fields:
                self.fields_list.addItem(tr("Nenhum campo de formulário encontrado."))
                return

            for field in fields:
                self._field_infos[field.name] = field
                item = QListWidgetItem(f"{field.name} — {field.field_type} — {field.value}")
                item.setData(Qt.ItemDataRole.UserRole, field.name)
                self.fields_list.addItem(item)

        run_task(
            self,
            tr("Campos de formulário"),
            task,
            on_success=done,
            error_message=tr("Falha ao listar campos: {error}"),
        )

    def _selected_field(self) -> str | None:
        item = self.fields_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _show_field(self, *_args):
        info = self._field_infos.get(self._selected_field() or "")
        self.edit_name_edit.setText(info.name.rpartition(".")[2] if info else "")
        self.edit_tooltip_edit.setText(info.tooltip if info else "")
        self.edit_read_only_box.setChecked(bool(info and info.read_only))
        self.edit_required_box.setChecked(bool(info and info.required))

    def _run_on_form(self, title: str, operation, success: str) -> None:
        """Roda `operation(entrada, saída)`, abre o resultado e lista os campos de novo."""
        input_path = self.session.path()
        output_path = self.edit_output_picker.path()
        if not input_path:
            notify_error(self, title, tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, title, tr("Escolha o arquivo de saída."))
            return

        def done(_result):
            self.session.open(output_path)
            self._list_fields()
            notify_success(self, title, success)

        run_task(
            self,
            title,
            call(operation, input_path, output_path),
            on_success=done,
            error_message=tr("Falha ao alterar o formulário: {error}"),
        )

    def _apply_field_edit(self):
        name = self._selected_field()
        if name is None:
            notify_error(self, tr("Campos de formulário"), tr("Escolha um campo da lista."))
            return
        options = {
            "new_name": self.edit_name_edit.text(),
            "tooltip": self.edit_tooltip_edit.text(),
            "read_only": self.edit_read_only_box.isChecked(),
            "required": self.edit_required_box.isChecked(),
        }
        self._run_on_form(
            tr("Campos de formulário"),
            lambda src, dst: EditFormField().run(src, dst, name, **options),
            tr("Campo alterado com sucesso."),
        )

    def _remove_field(self):
        name = self._selected_field()
        if name is None:
            notify_error(self, tr("Campos de formulário"), tr("Escolha um campo da lista."))
            return
        self._run_on_form(
            tr("Campos de formulário"),
            lambda src, dst: RemoveFormField().run(src, dst, name),
            tr('Campo "{name}" removido.').format(name=name),
        )

    def _apply_tab_order(self):
        mode = self.tab_order_combo.currentData()
        order = [
            name
            for row in range(self.fields_list.count())
            if (name := self.fields_list.item(row).data(Qt.ItemDataRole.UserRole))
        ]
        if mode == "list" and not order:
            notify_error(self, tr("Campos de formulário"), tr('Clique em "Listar campos" primeiro.'))
            return
        self._run_on_form(
            tr("Campos de formulário"),
            lambda src, dst: SetTabOrder().run(src, dst, mode=mode, order=order),
            tr("Ordem de tabulação gravada."),
        )

    # ---- Exportar dados -----------------------------------------------------

    def _build_export_panel(self, fmt: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        file_filter = "CSV (*.csv);;Excel (*.xlsx)" if fmt == "csv" else "FDF (*.fdf)"
        output_picker = FilePicker(mode="save", file_filter=file_filter)

        export_button = QPushButton(tr("Exportar"))
        self.action_buttons.append(export_button)
        export_button.clicked.connect(lambda: self._export_data(fmt, output_picker))

        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(output_picker)
        layout.addWidget(export_button)
        return widget

    def _export_data(self, fmt: str, output_picker: FilePicker):
        input_path = self.session.path()
        output_path = output_picker.path()

        if not input_path:
            notify_error(self, tr("Exportar dados"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Exportar dados"), tr("Escolha o arquivo de saída."))
            return

        operation = ExportFormDataCSV() if fmt == "csv" else ExportFormDataFDF()

        def done(count):
            notify_success(
                self, tr("Exportar dados"), tr("{count} campo(s) exportado(s) com sucesso.").format(count=count)
            )

        run_task(
            self,
            tr("Exportar dados"),
            call(operation.run, input_path, output_path),
            on_success=done,
            error_message=tr("Falha ao exportar dados: {error}"),
        )

    # ---- Importar dados -----------------------------------------------------

    def _build_import_panel(self, fmt: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        file_filter = "CSV (*.csv);;Excel (*.xlsx)" if fmt == "csv" else "FDF (*.fdf)"
        data_picker = FilePicker(mode="open", file_filter=file_filter)
        output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="preenchido"
        )

        import_button = QPushButton(tr("Importar"))
        self.action_buttons.append(import_button)
        import_button.clicked.connect(lambda: self._import_data(fmt, data_picker, output_picker))

        label = tr("Arquivo CSV ou Excel com os dados:") if fmt == "csv" else tr("Arquivo FDF com os dados:")
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
            notify_error(self, tr("Importar dados"), tr("Abra um PDF para começar."))
            return
        if not data_path:
            notify_error(self, tr("Importar dados"), tr("Escolha o arquivo de dados."))
            return
        if not output_path:
            notify_error(self, tr("Importar dados"), tr("Escolha o arquivo de saída."))
            return

        operation = ImportFormDataCSV() if fmt == "csv" else ImportFormDataFDF()

        def done(result):
            self.session.open(output_path)
            message = tr("{count} campo(s) preenchido(s) com sucesso.").format(count=result.filled)
            if result.not_found:
                message += "\n\n" + tr("Sem campo correspondente no PDF (ignorados): {names}").format(
                    names=", ".join(result.not_found)
                )
            notify_success(self, tr("Importar dados"), message)

        run_task(
            self,
            tr("Importar dados"),
            call(operation.run, input_path, output_path, data_path),
            on_success=done,
            error_message=tr("Falha ao importar dados: {error}"),
        )

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
        self.action_buttons.append(flatten_button)
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
            notify_error(self, tr("Achatar formulário"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Achatar formulário"), tr("Escolha o arquivo de saída."))
            return

        task = call(FlattenFormFields().run, input_path, output_path)

        def done(count):
            self.session.open(output_path)
            notify_success(
                self,
                tr("Achatar formulário"),
                tr("{count} campo(s) achatado(s) com sucesso.").format(count=count),
            )

        run_task(
            self,
            tr("Achatar formulário"),
            task,
            on_success=done,
            error_message=tr("Falha ao achatar formulário: {error}"),
        )
