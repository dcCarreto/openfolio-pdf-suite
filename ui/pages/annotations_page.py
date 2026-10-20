"""Aba de anotações e marcação: realce, sublinhado, riscado, notas, caneta e carimbo,
e os comentários já gravados no documento (editar, remover, XFDF)."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.annotations import (
    AddAnnotations,
    AnnotationInfo,
    ExportAnnotationsCSV,
    ListAnnotations,
    RemoveAnnotations,
    UpdateAnnotation,
)
from core.xfdf import ExportAnnotationsXFDF, ImportAnnotationsXFDF
from ui.annotation_state import AnnotationState, DEFAULT_COLOR
from ui.document_session import DocumentSession
from ui.errors import show_error
from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder
from ui.tasks import call, run_task
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

_KIND_LABELS = {
    "Text": "Nota",
    "Highlight": "Realce",
    "Underline": "Sublinhado",
    "StrikeOut": "Riscado",
    "Squiggly": "Ondulado",
    "Ink": "Caneta",
    "FreeText": "Texto livre",
    "Stamp": "Carimbo",
    "Square": "Retângulo",
    "Circle": "Círculo",
    "Line": "Linha",
    "Polygon": "Polígono",
    "PolyLine": "Polilinha",
    "Caret": "Inserção",
    "FileAttachment": "Anexo",
}

# O texto desses faz parte do desenho (/AP): trocar /Contents não mudaria o que aparece.
_DRAWN_TEXT_KINDS = {"FreeText", "Stamp"}


def format_pdf_date(value: str) -> str:
    """"D:20261019143000-03'00'" -> "19/10/2026 14:30" (vazio se não for uma data do PDF)."""
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", value or "")
    if not match:
        return ""
    year, month, day, hour, minute = match.groups()
    text = f"{day}/{month}/{year}"
    return f"{text} {hour}:{minute or '00'}" if hour else text


def describe_comment(comment: AnnotationInfo) -> str:
    parts = [
        f"{tr('Página')} {comment.page_index + 1}",
        tr(_KIND_LABELS.get(comment.kind, comment.kind)),
    ]
    parts += [value for value in (comment.author, format_pdf_date(comment.date)) if value]
    text = " · ".join(parts)
    first_line = comment.content.strip().splitlines()[0] if comment.content.strip() else ""
    return f"{text}\n{first_line[:80]}" if first_line else text


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
        self._stamp_entries: list[tuple[str, str | None, str | None] | None] = []  # (texto, cor, nome salvo)
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

        self._comments: list[AnnotationInfo] = []
        self.comments_list = QListWidget()
        self.comments_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.comments_list.itemSelectionChanged.connect(self._on_comment_selected)
        self.comment_text_edit = QPlainTextEdit()
        self.comment_text_edit.setMaximumHeight(90)
        self.comment_author_edit = QLineEdit()
        self.comment_author_edit.setPlaceholderText(tr("Autor"))
        self.update_comment_button = QPushButton(tr("Salvar alteração do comentário"))
        self.update_comment_button.clicked.connect(self._update_comment)
        self.remove_comments_button = QPushButton(tr("Remover comentários selecionados"))
        self.remove_comments_button.clicked.connect(self._remove_comments)
        import_xfdf_button = QPushButton(tr("Importar comentários (XFDF)..."))
        import_xfdf_button.clicked.connect(self._import_xfdf)
        session.path_changed.connect(self._load_comments)

        self.export_csv_picker = FilePicker(
            mode="save", file_filter="CSV (*.csv);;Excel (*.xlsx);;XFDF (*.xfdf)"
        )
        export_csv_button = QPushButton(tr("Exportar comentários (CSV, Excel ou XFDF)"))
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
        layout.addWidget(QLabel(tr("Comentários do documento:")))
        layout.addWidget(self.comments_list)
        layout.addWidget(self.comment_text_edit)
        layout.addWidget(self.comment_author_edit)
        layout.addWidget(self.update_comment_button)
        layout.addWidget(self.remove_comments_button)
        layout.addWidget(import_xfdf_button)
        layout.addWidget(QLabel(tr("Exportar comentários existentes:")))
        layout.addWidget(self.export_csv_picker)
        layout.addWidget(export_csv_button)

        self._load_comments()

    # ---- Comentários já gravados ----------------------------------------------------

    def _load_comments(self):
        """Relê a lista a cada versão do documento: as posições em /Annots que ela guarda
        só valem para o arquivo de onde foram lidas."""
        selected = {(c.page_index, c.index) for c in self._selected_comments()}
        input_path = self.session.path()
        try:
            self._comments = ListAnnotations().run(input_path) if input_path else []
        except Exception:
            self._comments = []  # PDF protegido ou ilegível: as outras ferramentas avisam
        self.comments_list.blockSignals(True)
        self.comments_list.clear()
        for comment in self._comments:
            self.comments_list.addItem(describe_comment(comment))
            if (comment.page_index, comment.index) in selected:
                self.comments_list.item(self.comments_list.count() - 1).setSelected(True)
        if not self._comments:
            self.comments_list.addItem(tr("Nenhum comentário no documento."))
            self.comments_list.item(0).setFlags(self.comments_list.item(0).flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.comments_list.blockSignals(False)
        self._on_comment_selected()

    def _selected_comments(self) -> list[AnnotationInfo]:
        rows = sorted(self.comments_list.row(item) for item in self.comments_list.selectedItems())
        return [self._comments[row] for row in rows if row < len(self._comments)]

    def _on_comment_selected(self):
        selected = self._selected_comments()
        single = selected[0] if len(selected) == 1 else None
        self.comment_text_edit.setPlainText(single.content if single else "")
        self.comment_author_edit.setText(single.author if single else "")
        drawn = single is not None and single.kind in _DRAWN_TEXT_KINDS
        self.comment_text_edit.setReadOnly(single is None or drawn)
        self.comment_text_edit.setToolTip(
            tr("O texto deste comentário faz parte do desenho: remova-o e crie outro.") if drawn else ""
        )
        self.comment_author_edit.setEnabled(single is not None)
        self.update_comment_button.setEnabled(single is not None)
        self.remove_comments_button.setEnabled(bool(selected))
        self.annotation_state.set_selected_comment(
            (single.page_index, single.rect) if single is not None and single.rect else None
        )

    def _apply_to_document(self, title: str, operation, message):
        """Roda `operation(entrada, saída)` numa versão nova do documento de trabalho
        (Ctrl+Z desfaz) e mostra `message(resultado)`."""
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, title, tr("Abra um PDF para começar."))
            return
        output_path = self.session.new_version_path()

        def done(result):
            self.session.open(output_path)
            text = message(result)
            if text:
                QMessageBox.information(self, title, text)

        run_task(self, title, call(operation, input_path, output_path), on_success=done)

    def _update_comment(self):
        selected = self._selected_comments()
        if len(selected) != 1:
            return
        comment = selected[0]
        content = comment.content if comment.kind in _DRAWN_TEXT_KINDS else self.comment_text_edit.toPlainText()
        author = self.comment_author_edit.text().strip()
        self._apply_to_document(
            tr("Editar comentário"),
            lambda source, output: UpdateAnnotation().run(
                source, output, comment.page_index, comment.index, content, author
            ),
            message=lambda _result: "",
        )

    def _remove_comments(self):
        items = [(c.page_index, c.index) for c in self._selected_comments()]
        if not items:
            return
        self._apply_to_document(
            tr("Remover comentários"),
            lambda source, output: RemoveAnnotations().run(source, output, items),
            message=lambda count: tr("{count} anotação(ões) removida(s), com popups e respostas.").format(
                count=count
            ),
        )

    def _import_xfdf(self):
        if not self.session.path():
            QMessageBox.warning(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        xfdf_path, _ = QFileDialog.getOpenFileName(
            self, tr("Importar comentários (XFDF)"), start_folder(), "XFDF (*.xfdf);;XML (*.xml)"
        )
        if not xfdf_path:
            return
        remember_folder_of(xfdf_path)

        def message(result):
            imported, skipped = result
            text = tr("{count} comentário(s) importado(s).").format(count=imported)
            if skipped:
                text += " " + tr(
                    "{count} ignorado(s): tipo não suportado, página que não existe ou dados inválidos."
                ).format(count=skipped)
            return text

        self._apply_to_document(
            tr("Importar comentários (XFDF)"),
            lambda source, output: ImportAnnotationsXFDF().run(source, xfdf_path, output),
            message=message,
        )

    def _reload_stamp_combo(self, select_name: str | None = None):
        self.stamp_combo.blockSignals(True)
        self.stamp_combo.clear()
        self._stamp_entries = []
        for text in _STAMP_TEXTS:
            label = tr(text)
            self.stamp_combo.addItem(label)
            self._stamp_entries.append((label, None, None))

        custom_stamps = self._stamp_library.list_stamps()
        if custom_stamps:
            self.stamp_combo.insertSeparator(self.stamp_combo.count())
            self._stamp_entries.append(None)
            for stamp in custom_stamps:
                self.stamp_combo.addItem(stamp.name)
                self._stamp_entries.append((stamp.text, stamp.color, stamp.name))
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
        text, color, _name = entry
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
            show_error(self, tr("Anotações"), tr("Falha ao salvar carimbo: {error}"), exc)
            return

        self.new_stamp_name_edit.clear()
        self._reload_stamp_combo(select_name=name)
        QMessageBox.information(self, tr("Anotações"), tr("Carimbo salvo com sucesso."))

    def _remove_custom_stamp(self):
        index = self.stamp_combo.currentIndex()
        entry = self._stamp_entries[index] if 0 <= index < len(self._stamp_entries) else None
        if entry is None or entry[2] is None:
            QMessageBox.warning(
                self, tr("Anotações"), tr("Selecione um carimbo customizado para remover.")
            )
            return

        # Pelo nome salvo: o combo é editável, e o texto dele pode já ter sido alterado.
        self._stamp_library.remove_stamp(entry[2])
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

        task = call(AddAnnotations().run, input_path, output_path, pending)

        def done(_result):
            self.annotation_state.clear_pending()
            self.session.open(output_path)
            QMessageBox.information(self, tr("Anotações"), tr("Anotações salvas com sucesso."))

        run_task(
            self,
            tr("Anotações"),
            task,
            on_success=done,
            error_message=tr("Falha ao salvar anotações: {error}"),
        )

    def _export_csv(self):
        input_path = self.session.path()
        output_path = self.export_csv_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Anotações"), tr("Escolha o arquivo de saída."))
            return

        if output_path.lower().endswith(".xfdf"):
            task = call(ExportAnnotationsXFDF().run, input_path, output_path)
        else:
            task = call(lambda *paths: (ExportAnnotationsCSV().run(*paths), 0), input_path, output_path)

        def done(result):
            count, skipped = result
            text = tr("{count} comentário(s) exportado(s) com sucesso.").format(count=count)
            if skipped:
                text += " " + tr("{count} de tipo que o XFDF daqui não leva (anexo, som...) ficou de fora.").format(
                    count=skipped
                )
            QMessageBox.information(self, tr("Anotações"), text)

        run_task(
            self,
            tr("Anotações"),
            task,
            on_success=done,
            error_message=tr("Falha ao exportar comentários: {error}"),
        )
