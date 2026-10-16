"""Aba de redação real e sanitização de PDFs."""

from PySide6.QtCore import Qt
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
)
from ui.i18n import tr
from ui.tasks import call, call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_PATTERN_CHECKBOX_LABELS = [
    ("cpf", "CPF"),
    ("cnpj", "CNPJ"),
    ("email", "E-mail"),
    ("phone", "Telefone"),
    ("credit_card", "Cartão de crédito"),
]
_KIND_LABELS = {**dict(_PATTERN_CHECKBOX_LABELS), CUSTOM_PATTERN_KIND: "Expressão personalizada"}


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
        items.append(tr("{count} script(s) ou ação(ões) de JavaScript").format(count=report.javascript))
    if report.external_actions:
        items.append(
            tr(
                "{count} ação(ões) que abrem arquivos ou programas, enviam dados ou acessam "
                "conteúdo externo"
            ).format(count=report.external_actions)
        )
    if report.embedded_files:
        items.append(tr("{count} arquivo(s) embutido(s)").format(count=report.embedded_files))
    if report.annotations_removed:
        items.append(tr("{count} anotação(ões)").format(count=report.annotations_removed))
    if report.private_data:
        items.append(
            tr(
                "{count} item(ns) de dados privados de aplicativos, miniaturas ou metadados "
                "de páginas e imagens"
            ).format(count=report.private_data)
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

    def __init__(self, session, redaction_state, parent=None):
        super().__init__(parent)
        self.session = session
        self.redaction_state = redaction_state

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Redigir"), tr("Sanitizar")])
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

        instructions = QLabel(
            tr(
                "Arraste no visualizador para marcar as áreas a apagar. Cada página marcada "
                "vira uma imagem, com as áreas pintadas de preto na própria imagem — e perde "
                "a camada de texto pesquisável inteira, não só a área marcada. O resultado é "
                "conferido antes de ser salvo."
            )
        )
        instructions.setWordWrap(True)

        detect_label = QLabel(
            tr("Ou detecte automaticamente padrões de dado sensível no texto do PDF:")
        )
        detect_label.setWordWrap(True)

        self.pattern_checkboxes: dict[str, QCheckBox] = {}
        for kind, label in _PATTERN_CHECKBOX_LABELS:
            checkbox = QCheckBox(tr(label))
            self.pattern_checkboxes[kind] = checkbox

        self.custom_pattern_edit = QLineEdit()
        self.custom_pattern_edit.setPlaceholderText(tr("Expressão regular personalizada (opcional)"))

        detect_button = QPushButton(tr("Detectar e marcar"))
        detect_button.clicked.connect(self._detect_patterns)

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

        self.redaction_state.pending_changed.connect(self._refresh_pending)
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
        redact_button.clicked.connect(self._apply_redaction)

        layout.addWidget(instructions)
        layout.addWidget(detect_label)
        for checkbox in self.pattern_checkboxes.values():
            layout.addWidget(checkbox)
        layout.addWidget(self.custom_pattern_edit)
        layout.addWidget(detect_button)
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
        sanitize_button.clicked.connect(self._apply_sanitize)

        layout.addWidget(self.remove_metadata_checkbox)
        layout.addWidget(self.remove_annotations_checkbox)
        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.sanitize_output_picker)
        layout.addWidget(sanitize_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    # -- lista de áreas pendentes -------------------------------------------------------

    def _refresh_pending(self):
        pending = self.redaction_state.pending()
        self.pending_label.setText(
            tr("{count} área(s) marcada(s) para redação").format(count=len(pending))
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
            QMessageBox.warning(self, tr("Redigir"), tr("Selecione na lista as áreas a remover."))
            return
        self.redaction_state.remove_many(rects)

    # -- ações -------------------------------------------------------------------------

    def _detect_patterns(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("Redigir"), tr("Abra um PDF para começar."))
            return

        kinds = [kind for kind, checkbox in self.pattern_checkboxes.items() if checkbox.isChecked()]
        custom_pattern = self.custom_pattern_edit.text().strip()
        if not kinds and not custom_pattern:
            QMessageBox.warning(
                self,
                tr("Redigir"),
                tr("Marque ao menos um padrão ou digite uma expressão regular."),
            )
            return

        task = call_with_progress(
            FindSensitiveData().run, input_path, kinds=kinds, custom_pattern=custom_pattern or None
        )

        def done(rects):
            added = self.redaction_state.add_many(rects)
            QMessageBox.information(
                self,
                tr("Redigir"),
                tr(
                    "{count} ocorrência(s) encontrada(s), {added} nova(s) marcada(s) para redação. "
                    "Revise a lista antes de aplicar."
                ).format(count=len(rects), added=added),
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
            QMessageBox.warning(self, tr("Redigir"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Redigir"), tr("Escolha o arquivo de saída."))
            return
        if not rects:
            QMessageBox.warning(
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
            message = tr("{count} página(s) redigida(s) com sucesso.").format(count=pages_redacted)
            if report is not None:
                message += "\n\n" + format_sanitize_report(report)
            QMessageBox.information(self, tr("Redigir"), message)

        run_task(
            self, tr("Redigir"), redact, on_success=done, error_message=tr("Falha ao redigir: {error}")
        )

    def _apply_sanitize(self):
        input_path = self.session.path()
        output_path = self.sanitize_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Sanitizar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Sanitizar"), tr("Escolha o arquivo de saída."))
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
            QMessageBox.information(
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
