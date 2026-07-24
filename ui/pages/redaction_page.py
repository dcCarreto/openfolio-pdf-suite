"""Aba de redação real e sanitização de PDFs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.redaction import RedactDocument, SanitizeDocument
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


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

        self.pending_label = QLabel()
        self.redaction_state.pending_changed.connect(self._update_pending_label)
        self._update_pending_label()

        clear_button = QPushButton(tr("Limpar pendentes"))
        clear_button.clicked.connect(self.redaction_state.clear_pending)

        self.redact_output_picker = FilePicker(mode="save")
        redact_button = QPushButton(tr("Aplicar redação"))
        redact_button.clicked.connect(self._apply_redaction)

        layout.addWidget(instructions)
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

        self.sanitize_output_picker = FilePicker(mode="save")
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
