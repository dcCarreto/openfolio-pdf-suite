"""Aba de redação real e sanitização de PDFs."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.redaction import (
    CUSTOM_PATTERN_KIND,
    FindSensitiveData,
    RedactDocument,
    RedactionRect,
    SanitizeDocument,
    SanitizeReport,
    TEXT_KIND,
)
from ui.i18n import plural, tr
from ui.pending_history import PendingHistory
from ui.tasks import call, call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success

_PATTERN_CHECKBOX_LABELS = [
    ("cpf", "CPF"),
    ("cnpj", "CNPJ"),
    ("email", "E-mail"),
    ("phone", "Telefone"),
    ("credit_card", "Cartão de crédito"),
]
_KIND_LABELS = {
    **dict(_PATTERN_CHECKBOX_LABELS),
    CUSTOM_PATTERN_KIND: "Expressão personalizada",
    TEXT_KIND: "Texto buscado",
}


def describe_redaction_rect(rect: RedactionRect) -> str:
    """Texto de uma área pendente na lista de revisão."""
    page = tr("Página {number}").format(number=rect.page_index + 1)
    if rect.kind:
        label = tr(_KIND_LABELS.get(rect.kind, rect.kind))
        return f"{page} — {label}: {rect.text}" if rect.text else f"{page} — {label}"
    return f"{page} — {tr('área marcada à mão')}"


def format_sanitize_report(report: SanitizeReport) -> str:
    """Resumo, para o usuário, do que a sanitização removeu."""
    items = []
    if report.javascript:
        items.append(plural(report.javascript, "1 script ou ação de JavaScript", "{count} scripts ou ações de JavaScript"))
    if report.external_actions:
        items.append(
            plural(
                report.external_actions,
                "1 ação que abre arquivos ou programas, envia dados ou acessa conteúdo externo",
                "{count} ações que abrem arquivos ou programas, enviam dados ou acessam conteúdo externo",
            )
        )
    if report.embedded_files:
        items.append(plural(report.embedded_files, "1 arquivo embutido", "{count} arquivos embutidos"))
    if report.annotations_removed:
        items.append(plural(report.annotations_removed, "1 anotação", "{count} anotações"))
    if report.private_data:
        items.append(
            plural(
                report.private_data,
                "1 item de dados privados de aplicativos, miniaturas ou metadados de páginas e imagens",
                "{count} itens de dados privados de aplicativos, miniaturas ou metadados de páginas e imagens",
            )
        )
    if report.metadata_removed:
        items.append(tr("metadados do documento (título, autor e outros)"))
    if report.xfa_removed:
        items.append(tr("formulário XFA (pode conter scripts)"))

    if not items:
        return tr("Nada perigoso foi encontrado no documento.")
    return tr("Removido:") + "\n" + "\n".join(f"• {item}" for item in items)


class RedactionPage(QWidget):
    """Permite apagar definitivamente áreas de um PDF (marcadas no visualizador) ou
    sanitizar o documento antes de compartilhar (remover metadados, JavaScript, anexos e,
    opcionalmente, anotações)."""

    edits_changed = Signal()  # as áreas marcadas mudaram: desfazer/refazer delas podem ter mudado
    edit_label = "área de redação"  # o "Desfazer área de redação" do menu

    def __init__(self, session, redaction_state, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.redaction_state = redaction_state

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        # Áreas e Textos e padrões marcam áreas na mesma lista e aplicam a mesma redação: só
        # muda como elas são marcadas. O índice 1 continua sendo Sanitizar.
        self.mode_combo.addItems([tr("Áreas"), tr("Sanitizar"), tr("Textos e padrões")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_redact_panel())
        self.stack.addWidget(self._build_sanitize_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_redact_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.drag_hint = QLabel(tr("Arraste no visualizador para marcar as áreas a apagar."))
        self.drag_hint.setWordWrap(True)
        instructions = QLabel(
            tr(
                "Cada página marcada vira uma imagem, com as áreas pintadas de preto na própria "
                "imagem — e perde a camada de texto pesquisável inteira, não só a área marcada. "
                "O resultado é conferido antes de ser salvo."
            )
        )
        instructions.setObjectName("pageSubtitle")
        instructions.setWordWrap(True)

        search_label = QLabel(tr("Textos a procurar"))
        search_label.setProperty("ofRole", "field")
        self.search_text_edit = QLineEdit()
        self.search_text_edit.setPlaceholderText(tr("Ex.: Maria da Silva; Rua das Flores"))
        search_label.setBuddy(self.search_text_edit)
        search_help = QLabel(
            tr("Todas as ocorrências são marcadas. Maiúsculas e acentos não importam; separe vários com ;")
        )
        search_help.setProperty("ofRole", "help")
        search_help.setWordWrap(True)
        self.search_text_edit.setAccessibleDescription(search_help.text())

        detect_label = QLabel(tr("Padrões de dado sensível"))
        detect_label.setProperty("ofRole", "field")

        self.pattern_checkboxes: dict[str, QCheckBox] = {}
        for kind, label in _PATTERN_CHECKBOX_LABELS:
            checkbox = QCheckBox(tr(label))
            self.pattern_checkboxes[kind] = checkbox

        self.custom_pattern_edit = QLineEdit()
        self.custom_pattern_edit.setPlaceholderText(tr("Expressão regular personalizada (opcional)"))

        detect_button = QPushButton(tr("Procurar e marcar"))
        detect_button.clicked.connect(self._detect_patterns)
        self.search_text_edit.returnPressed.connect(self._detect_patterns)

        self.pending_label = QLabel()
        self.pending_list = QListWidget()
        self.pending_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pending_list.setToolTip(tr("Selecione uma área para vê-la destacada no visualizador."))
        self.pending_list.currentItemChanged.connect(self._on_current_pending_changed)

        remove_selected_button = QPushButton(tr("Remover selecionadas"))
        remove_selected_button.clicked.connect(self._remove_selected_pending)
        clear_button = QPushButton(tr("Limpar todas"))
        clear_button.clicked.connect(self.redaction_state.clear_pending)
        pending_buttons = QHBoxLayout()
        pending_buttons.addWidget(remove_selected_button)
        pending_buttons.addWidget(clear_button)

        self._history = PendingHistory(self.redaction_state, self.redaction_state.set_pending)
        self.redaction_state.pending_changed.connect(self._on_pending_changed)
        # Ligado depois do visualizador, que limpa as pendentes ao trocar de arquivo.
        self.session.path_changed.connect(self._on_document_changed)
        self._refresh_pending()

        self.also_sanitize_checkbox = QCheckBox(tr("Também sanitizar o documento"))
        self.also_sanitize_checkbox.setChecked(True)
        # QCheckBox não quebra linha: a explicação fica num QLabel à parte, para não alargar
        # o painel (de largura fixa) além do espaço disponível.
        sanitize_hint = QLabel(
            tr(
                "O texto apagado pode aparecer também no título, nos metadados ou em anexos. "
                "Com esta opção, o arquivo redigido também passa pela sanitização."
            )
        )
        sanitize_hint.setObjectName("pageSubtitle")
        sanitize_hint.setWordWrap(True)

        self.redact_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="redigido"
        )
        redact_button = QPushButton(tr("Aplicar redação"))
        self.action_buttons.append(redact_button)
        redact_button.clicked.connect(self._apply_redaction)

        # A procura só aparece no modo Textos e padrões; o resto é das duas formas de marcar.
        self.search_box = QWidget()
        search_layout = QVBoxLayout(self.search_box)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_text_edit)
        search_layout.addWidget(search_help)
        search_layout.addSpacing(4)
        search_layout.addWidget(detect_label)
        for checkbox in self.pattern_checkboxes.values():
            search_layout.addWidget(checkbox)
        search_layout.addWidget(self.custom_pattern_edit)
        search_layout.addWidget(detect_button)
        self.search_box.hide()

        layout.addWidget(self.drag_hint)
        layout.addWidget(self.search_box)
        layout.addWidget(instructions)
        layout.addWidget(self.pending_label)
        layout.addWidget(self.pending_list)
        layout.addLayout(pending_buttons)
        layout.addWidget(self.also_sanitize_checkbox)
        layout.addWidget(sanitize_hint)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.redact_output_picker)
        layout.addWidget(redact_button)
        return widget

    def _build_sanitize_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.remove_metadata_checkbox = QCheckBox(tr("Remover metadados"))
        self.remove_metadata_checkbox.setChecked(True)
        self.remove_annotations_checkbox = QCheckBox(tr("Remover anotações e comentários"))
        self.remove_annotations_checkbox.setChecked(False)

        note = QLabel(
            tr(
                "JavaScript, ações que abrem arquivos ou programas ou enviam dados, e arquivos "
                "embutidos são sempre removidos. O resultado é conferido antes de ser salvo."
            )
        )
        note.setWordWrap(True)

        self.sanitize_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="sanitizado"
        )
        sanitize_button = QPushButton(tr("Sanitizar"))
        self.action_buttons.append(sanitize_button)
        sanitize_button.clicked.connect(self._apply_sanitize)

        layout.addWidget(self.remove_metadata_checkbox)
        layout.addWidget(self.remove_annotations_checkbox)
        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.sanitize_output_picker)
        layout.addWidget(sanitize_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(1 if index == 1 else 0)
        self.drag_hint.setVisible(index == 0)
        self.search_box.setVisible(index == 2)

    # -- lista de áreas pendentes -------------------------------------------------------

    def _on_pending_changed(self):
        self._history.changed()
        self._refresh_pending()
        self.edits_changed.emit()

    def _on_document_changed(self):
        self._history.reset()
        self.edits_changed.emit()

    # Ctrl+Z / Ctrl+Y da janela: as áreas marcadas vêm antes das versões do documento.

    def can_undo_edit(self) -> bool:
        return self._history.can_undo()

    def can_redo_edit(self) -> bool:
        return self._history.can_redo()

    def undo_edit(self) -> None:
        self._history.undo()

    def redo_edit(self) -> None:
        self._history.redo()

    def _refresh_pending(self):
        pending = self.redaction_state.pending()
        self.pending_label.setText(
            plural(len(pending), "1 área marcada para redação", "{count} áreas marcadas para redação")
        )
        selected = self.redaction_state.selected()
        self.pending_list.blockSignals(True)
        self.pending_list.clear()
        for rect in sorted(pending, key=lambda r: (r.page_index, -r.top, r.left)):
            item = QListWidgetItem(describe_redaction_rect(rect))
            item.setData(Qt.ItemDataRole.UserRole, rect)
            self.pending_list.addItem(item)
            if rect == selected:
                self.pending_list.setCurrentItem(item)
        self.pending_list.blockSignals(False)

    def _on_current_pending_changed(self, current: QListWidgetItem | None, _previous=None):
        rect = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.redaction_state.set_selected(rect)

    def _remove_selected_pending(self):
        rects = [item.data(Qt.ItemDataRole.UserRole) for item in self.pending_list.selectedItems()]
        if not rects:
            notify_error(self, tr("Redigir"), tr("Selecione na lista as áreas a remover."))
            return
        self.redaction_state.remove_many(rects)

    # -- ações -------------------------------------------------------------------------

    def _detect_patterns(self):
        input_path = self.session.path()
        if not input_path:
            notify_error(self, tr("Redigir"), tr("Abra um PDF para começar."))
            return

        kinds = [kind for kind, checkbox in self.pattern_checkboxes.items() if checkbox.isChecked()]
        custom_pattern = self.custom_pattern_edit.text().strip()
        search_text = self.search_text_edit.text().strip()
        if not kinds and not custom_pattern and not search_text.strip(";"):
            notify_error(
                self,
                tr("Redigir"),
                tr("Digite um texto a procurar, marque um padrão ou digite uma expressão regular."),
            )
            return

        task = call_with_progress(
            FindSensitiveData().run,
            input_path,
            kinds=kinds,
            custom_pattern=custom_pattern or None,
            search_text=search_text or None,
        )

        def done(rects):
            added = self.redaction_state.add_many(rects)
            notify_success(
                self,
                tr("Redigir"),
                plural(len(rects), "1 ocorrência encontrada", "{count} ocorrências encontradas")
                + ", "
                + plural(added, "1 nova marcada para redação.", "{count} novas marcadas para redação.")
                + " "
                + tr("Revise a lista antes de aplicar."),
            )

        run_task(
            self,
            tr("Redigir"),
            task,
            on_success=done,
            error_message=tr("Falha ao detectar padrões: {error}"),
        )

    def _apply_redaction(self):
        input_path = self.session.path()
        output_path = self.redact_output_picker.path()
        rects = self.redaction_state.pending()

        if not input_path:
            notify_error(self, tr("Redigir"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Redigir"), tr("Escolha o arquivo de saída."))
            return
        if not rects:
            notify_error(
                self, tr("Redigir"), tr("Marque pelo menos uma área no visualizador antes de aplicar.")
            )
            return

        confirmation = QMessageBox.question(
            self,
            tr("Redigir"),
            tr(
                "A redação é irreversível: cada página marcada vira uma imagem achatada e "
                "perde toda a camada de texto pesquisável, não só a área marcada. Continuar?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        rects = list(rects)
        also_sanitize = self.also_sanitize_checkbox.isChecked()

        def redact(progress):
            pages_redacted = RedactDocument().run(input_path, output_path, rects, progress=progress)
            report = SanitizeDocument().run(output_path, output_path) if also_sanitize else None
            return pages_redacted, report

        def done(result):
            pages_redacted, report = result
            self.redaction_state.clear_pending()
            self.session.open(output_path)
            message = plural(pages_redacted, "1 página redigida.", "{count} páginas redigidas.")
            if report is not None:
                message += "\n\n" + format_sanitize_report(report)
            notify_success(self, tr("Redigir"), message)

        run_task(
            self, tr("Redigir"), redact, on_success=done, error_message=tr("Falha ao redigir: {error}")
        )

    def _apply_sanitize(self):
        input_path = self.session.path()
        output_path = self.sanitize_output_picker.path()

        if not input_path:
            notify_error(self, tr("Sanitizar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Sanitizar"), tr("Escolha o arquivo de saída."))
            return

        task = call(
            SanitizeDocument().run,
            input_path,
            output_path,
            remove_metadata=self.remove_metadata_checkbox.isChecked(),
            remove_annotations=self.remove_annotations_checkbox.isChecked(),
        )

        def done(report):
            self.session.open(output_path)
            notify_success(
                self,
                tr("Sanitizar"),
                tr("PDF sanitizado com sucesso.") + "\n\n" + format_sanitize_report(report),
            )

        run_task(
            self,
            tr("Sanitizar"),
            task,
            on_success=done,
            error_message=tr("Falha ao sanitizar: {error}"),
        )
