"""Aba de conversão e verificação de PDF/A (arquivamento)."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.pdfa import VALID_CONFORMANCE, ConvertToPDFA, ValidatePDFA
from ui.i18n import tr, tr_message
from ui.tasks import call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_PARTS = [1, 2, 3]
_CONFORMANCE_LABELS = {
    "A": "A (acessível)",
    "B": "B (básica)",
    "U": "U (Unicode)",
}


def _bullets(items) -> str:
    return "\n".join("• " + tr_message(item) for item in items)


class PDFAPage(QWidget):
    """Permite converter um PDF para PDF/A (arquivamento) ou verificar se um PDF atende aos
    requisitos de PDF/A que a ferramenta cobre."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Converter para PDF/A"), tr("Validar PDF/A")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_convert_panel())
        self.stack.addWidget(self._build_validate_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_convert_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Remove o que o PDF/A proíbe (JavaScript, ações automáticas, anexos não "
                "permitidos), embute o perfil de cor sRGB e sincroniza os metadados. Depois "
                "verifica fontes, transparência e estrutura: se algo impedir a conformidade, "
                "nada é gravado e a lista do que falta é mostrada. PDFs protegidos por senha "
                'precisam passar antes por "Remover senha".'
            )
        )
        note.setWordWrap(True)

        self.convert_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="pdfa"
        )

        self.convert_part_combo = QComboBox()
        for part in _PARTS:
            self.convert_part_combo.addItem(f"PDF/A-{part}", part)
        self.convert_part_combo.setCurrentIndex(1)  # parte 2, o padrão mais comum
        self.convert_part_combo.currentIndexChanged.connect(self._update_conformance_options)

        self.convert_conformance_combo = QComboBox()
        self._update_conformance_options()

        apply_button = QPushButton(tr("Converter"))
        apply_button.clicked.connect(self._apply_convert)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.convert_output_picker)
        layout.addWidget(QLabel(tr("Parte (PDF/A-N):")))
        layout.addWidget(self.convert_part_combo)
        layout.addWidget(QLabel(tr("Nível de conformidade:")))
        layout.addWidget(self.convert_conformance_combo)
        layout.addWidget(apply_button)
        return widget

    def _update_conformance_options(self):
        current = self.convert_conformance_combo.currentData() or "B"
        self.convert_conformance_combo.clear()
        for level in VALID_CONFORMANCE[self.convert_part_combo.currentData()]:
            self.convert_conformance_combo.addItem(tr(_CONFORMANCE_LABELS[level]), level)
        index = self.convert_conformance_combo.findData(current)
        self.convert_conformance_combo.setCurrentIndex(index if index >= 0 else self.convert_conformance_combo.findData("B"))

    def _build_validate_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Verifica os requisitos de PDF/A que o app cobre (declaração, perfil de cor, "
                "fontes embutidas, transparência, ações e anexos proibidos, metadados) — não é "
                "a validação ISO 19005 completa."
            )
        )
        note.setWordWrap(True)

        validate_button = QPushButton(tr("Validar"))
        validate_button.clicked.connect(self._apply_validate)

        layout.addWidget(note)
        layout.addWidget(validate_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _apply_convert(self):
        input_path = self.session.path()
        output_path = self.convert_output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("PDF/A"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("PDF/A"), tr("Escolha o arquivo de saída."))
            return

        task = call_with_progress(
            ConvertToPDFA().run,
            input_path,
            output_path,
            part=self.convert_part_combo.currentData(),
            conformance=self.convert_conformance_combo.currentData(),
        )

        def done(result):
            if not result.written:
                message = tr("O documento não pôde ser convertido, e nada foi gravado:") + "\n" + _bullets(result.issues)
                QMessageBox.warning(self, tr("PDF/A"), message)
                return
            self.session.open(output_path)
            message = tr("PDF convertido com sucesso.")
            if result.fixed:
                message += "\n\n" + tr("Ajustes feitos:") + "\n" + _bullets(result.fixed)
            QMessageBox.information(self, tr("PDF/A"), message)

        run_task(
            self,
            tr("PDF/A"),
            task,
            on_success=done,
            error_message=tr("Falha ao converter: {error}"),
        )

    def _apply_validate(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("PDF/A"), tr("Abra um PDF para começar."))
            return

        task = call_with_progress(ValidatePDFA().run, input_path)

        def done(result):
            if result.is_valid:
                text = tr(
                    "Nenhum problema encontrado nas verificações do app. Elas não cobrem a "
                    "norma inteira: para arquivamento legal, confirme com o veraPDF."
                )
                QMessageBox.information(self, tr("PDF/A"), text)
            else:
                QMessageBox.warning(
                    self,
                    tr("PDF/A"),
                    tr("Problemas encontrados:\n{issues}").format(issues=_bullets(result.issues)),
                )

        run_task(
            self,
            tr("PDF/A"),
            task,
            on_success=done,
            error_message=tr("Falha ao validar: {error}"),
        )
