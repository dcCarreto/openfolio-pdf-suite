"""Aba de redação real e sanitização de PDFs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.redaction import FindSensitiveData, RedactDocument, SanitizeDocument
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_PATTERN_CHECKBOX_LABELS = [
    ("cpf", "CPF"),
    ("cnpj", "CNPJ"),
    ("email", "E-mail"),
    ("phone", "Telefone"),
    ("credit_card", "Cartão de crédito"),
]


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
                "vira uma imagem achatada (perde a camada de texto pesquisável inteira, não "
                "só a área marcada) — é assim que garantimos que nada fique recuperável."
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
        self.redaction_state.pending_changed.connect(self._update_pending_label)
        self._update_pending_label()

        clear_button = QPushButton(tr("Limpar pendentes"))
        clear_button.clicked.connect(self.redaction_state.clear_pending)

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
        layout.addWidget(clear_button)
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

        note = QLabel(tr("JavaScript e anexos embutidos são sempre removidos."))
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

    def _update_pending_label(self):
        count = len(self.redaction_state.pending())
        self.pending_label.setText(tr("{count} área(s) marcada(s) para redação").format(count=count))

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

        try:
            rects = FindSensitiveData().run(input_path, kinds=kinds, custom_pattern=custom_pattern or None)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Redigir"), tr("Falha ao detectar padrões: {error}").format(error=exc)
            )
            return

        for rect in rects:
            self.redaction_state.add_pending(rect)

        QMessageBox.information(
            self,
            tr("Redigir"),
            tr("{count} ocorrência(s) encontrada(s) e marcada(s) para redação.").format(
                count=len(rects)
            ),
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

        try:
            pages_redacted = RedactDocument().run(input_path, output_path, rects)
        except Exception as exc:
            QMessageBox.critical(self, tr("Redigir"), tr("Falha ao redigir: {error}").format(error=exc))
            return

        self.redaction_state.clear_pending()
        self.session.open(output_path)
        QMessageBox.information(
            self, tr("Redigir"), tr("{count} página(s) redigida(s) com sucesso.").format(count=pages_redacted)
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

        try:
            SanitizeDocument().run(
                input_path,
                output_path,
                remove_metadata=self.remove_metadata_checkbox.isChecked(),
                remove_annotations=self.remove_annotations_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, tr("Sanitizar"), tr("Falha ao sanitizar: {error}").format(error=exc))
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Sanitizar"), tr("PDF sanitizado com sucesso."))
