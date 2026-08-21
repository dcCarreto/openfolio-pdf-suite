"""Aba de anotações e marcação: realce, sublinhado, riscado, notas, caneta e carimbo."""

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.annotations import AddAnnotations, ExportAnnotationsCSV
from ui.annotation_state import AnnotationState, DEFAULT_COLOR
from ui.document_session import DocumentSession
from ui.i18n import tr
from ui.stamp_library import StampLibrary
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_TOOLS = [
    ("select", "Selecionar/Apagar"),
    ("highlight", "Realce"),
    ("underline", "Sublinhado"),
    ("strikeout", "Riscado"),
    ("note", "Nota adesiva"),
    ("ink", "Caneta"),
    ("stamp", "Carimbo"),
]

_COLORS = [
    ("ffeb3b", "Amarelo"),
    ("f44336", "Vermelho"),
    ("4caf50", "Verde"),
    ("2196f3", "Azul"),
    ("000000", "Preto"),
]

_STAMP_TEXTS = ["APROVADO", "CONFIDENCIAL", "RASCUNHO", "REVISADO", "URGENTE"]


class AnnotationsPage(QWidget):
    """Permite marcar o PDF aberto (realce, sublinhado, riscado, notas, caneta, carimbo)
    diretamente sobre o visualizador central, e gravar o resultado em um novo arquivo."""

    def __init__(self, session: DocumentSession, annotation_state: AnnotationState, parent=None):
        super().__init__(parent)
        self.session = session
        self.annotation_state = annotation_state

        self.source_bar = DocumentSourceBar(session)

        self.tool_buttons: dict[str, QPushButton] = {}
        tools_layout = QVBoxLayout()
        tool_group = QButtonGroup(self)
        tool_group.setExclusive(True)
        self._tool_group = tool_group
        for key, label in _TOOLS:
            button = QPushButton(tr(label))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, k=key: self.annotation_state.set_tool(k))
            tool_group.addButton(button)
            tools_layout.addWidget(button)
            self.tool_buttons[key] = button

        current_tool = annotation_state.active_tool() or "select"
        annotation_state.set_tool(current_tool)
        self.tool_buttons[current_tool].setChecked(True)

        self.color_buttons: dict[str, QPushButton] = {}
        colors_layout = QHBoxLayout()
        color_group = QButtonGroup(self)
        color_group.setExclusive(True)
        self._color_group = color_group
        for color, name in _COLORS:
            button = QPushButton()
            button.setObjectName("colorSwatch")
            button.setCheckable(True)
            button.setFixedSize(26, 26)
            button.setToolTip(tr(name))
            button.setStyleSheet(
                f"QPushButton {{ background-color: #{color}; border: 2px solid transparent; "
                "border-radius: 4px; }"
                "QPushButton:checked { border: 2px solid #ffffff; }"
            )
            button.clicked.connect(lambda _checked, c=color: self.annotation_state.set_color(c))
            color_group.addButton(button)
            colors_layout.addWidget(button)
            self.color_buttons[color] = button
        colors_layout.addStretch()
        self.color_buttons.get(annotation_state.active_color(), self.color_buttons[DEFAULT_COLOR]).setChecked(True)

        self.stamp_label = QLabel(tr("Texto do carimbo:"))
        self.stamp_combo = QComboBox()
        self.stamp_combo.setEditable(True)
        self.stamp_combo.currentIndexChanged.connect(self._on_stamp_index_changed)
        self.stamp_combo.editTextChanged.connect(self._on_stamp_text_edited)

        self._stamp_library = StampLibrary()
        self._stamp_entries: list[tuple[str, str | None] | None] = []
        self._reload_stamp_combo()

        self.new_stamp_name_edit = QLineEdit()
        self.new_stamp_name_edit.setPlaceholderText(tr("Nome para salvar este carimbo (opcional)"))
        save_stamp_button = QPushButton(tr("Salvar carimbo customizado"))
        save_stamp_button.clicked.connect(self._save_custom_stamp)
        remove_stamp_button = QPushButton(tr("Remover carimbo customizado selecionado"))
        remove_stamp_button.clicked.connect(self._remove_custom_stamp)
        self._stamp_extra_widgets = [
            self.new_stamp_name_edit,
            save_stamp_button,
            remove_stamp_button,
        ]

        annotation_state.tool_changed.connect(self._update_stamp_visibility)
        self._update_stamp_visibility()

        self.pending_label = QLabel()
        clear_button = QPushButton(tr("Limpar pendentes"))
        clear_button.clicked.connect(self.annotation_state.clear_pending)
        annotation_state.pending_changed.connect(self._update_pending_label)
        self._update_pending_label()

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="anotado"
        )
        save_button = QPushButton(tr("Salvar anotações"))
        save_button.clicked.connect(self._save)

        self.export_csv_picker = FilePicker(mode="save", file_filter="CSV (*.csv)")
        export_csv_button = QPushButton(tr("Exportar comentários (CSV)"))
        export_csv_button.clicked.connect(self._export_csv)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Ferramenta:")))
        layout.addLayout(tools_layout)
        layout.addWidget(QLabel(tr("Cor:")))
        layout.addLayout(colors_layout)
        layout.addWidget(self.stamp_label)
        layout.addWidget(self.stamp_combo)
        layout.addWidget(self.new_stamp_name_edit)
        layout.addWidget(save_stamp_button)
        layout.addWidget(remove_stamp_button)
        layout.addWidget(self.pending_label)
        layout.addWidget(clear_button)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)
        layout.addWidget(QLabel(tr("Exportar comentários existentes para CSV:")))
        layout.addWidget(self.export_csv_picker)
        layout.addWidget(export_csv_button)

    def _reload_stamp_combo(self, select_name: str | None = None):
        self.stamp_combo.blockSignals(True)
        self.stamp_combo.clear()
        self._stamp_entries = []
        for text in _STAMP_TEXTS:
            label = tr(text)
            self.stamp_combo.addItem(label)
            self._stamp_entries.append((label, None))

        custom_stamps = self._stamp_library.list_stamps()
        if custom_stamps:
            self.stamp_combo.insertSeparator(self.stamp_combo.count())
            self._stamp_entries.append(None)
            for stamp in custom_stamps:
                self.stamp_combo.addItem(stamp.name)
                self._stamp_entries.append((stamp.text, stamp.color))
        self.stamp_combo.blockSignals(False)

        target_index = 0
        if select_name is not None:
            found = self.stamp_combo.findText(select_name)
            if found >= 0:
                target_index = found
        self.stamp_combo.setCurrentIndex(target_index)
        self._apply_stamp_entry(target_index)

    def _apply_stamp_entry(self, index: int):
        if not (0 <= index < len(self._stamp_entries)):
            return
        entry = self._stamp_entries[index]
        if entry is None:
            return
        text, color = entry
        self.annotation_state.set_stamp_text(text)
        if color is not None:
            self.annotation_state.set_color(color)
            button = self.color_buttons.get(color)
            if button is not None:
                button.setChecked(True)

    def _on_stamp_index_changed(self, index: int):
        self._apply_stamp_entry(index)

    def _on_stamp_text_edited(self, text: str):
        self.annotation_state.set_stamp_text(text)

    def _save_custom_stamp(self):
        text = self.stamp_combo.currentText().strip()
        if not text:
            QMessageBox.warning(self, tr("Anotações"), tr("Digite o texto do carimbo antes de salvar."))
            return
        name = self.new_stamp_name_edit.text().strip() or text

        try:
            self._stamp_library.add_stamp(name, text, color=self.annotation_state.active_color())
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anotações"), tr("Falha ao salvar carimbo: {error}").format(error=exc)
            )
            return

        self.new_stamp_name_edit.clear()
        self._reload_stamp_combo(select_name=name)
        QMessageBox.information(self, tr("Anotações"), tr("Carimbo salvo com sucesso."))

    def _remove_custom_stamp(self):
        index = self.stamp_combo.currentIndex()
        entry = self._stamp_entries[index] if 0 <= index < len(self._stamp_entries) else None
        if entry is None or entry[1] is None:
            QMessageBox.warning(
                self, tr("Anotações"), tr("Selecione um carimbo customizado para remover.")
            )
            return

        self._stamp_library.remove_stamp(self.stamp_combo.currentText())
        self._reload_stamp_combo()

    def _update_stamp_visibility(self):
        is_stamp = self.annotation_state.active_tool() == "stamp"
        self.stamp_label.setVisible(is_stamp)
        self.stamp_combo.setVisible(is_stamp)
        for widget in self._stamp_extra_widgets:
            widget.setVisible(is_stamp)

    def _update_pending_label(self):
        count = len(self.annotation_state.pending())
        self.pending_label.setText(tr("{count} anotação(ões) pendente(s)").format(count=count))

    def _save(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()
        pending = self.annotation_state.pending()

        if not input_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return
        if not pending:
            QMessageBox.warning(
                self, tr("Anotações"), tr("Adicione pelo menos uma anotação antes de salvar.")
            )
            return

        try:
            AddAnnotations().run(input_path, output_path, pending)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anotações"), tr("Falha ao salvar anotações: {error}").format(error=exc)
            )
            return

        self.annotation_state.clear_pending()
        self.session.open(output_path)
        QMessageBox.information(self, tr("Anotações"), tr("Anotações salvas com sucesso."))

    def _export_csv(self):
        input_path = self.session.path()
        output_path = self.export_csv_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return

        try:
            count = ExportAnnotationsCSV().run(input_path, output_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Anotações"), tr("Falha ao exportar comentários: {error}").format(error=exc)
            )
            return

        QMessageBox.information(
            self,
            tr("Anotações"),
            tr("{count} comentário(s) exportado(s) com sucesso.").format(count=count),
        )
