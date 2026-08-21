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

from core.pdfa import ConvertToPDFA, ValidatePDFA
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_PARTS = ["1", "2", "3"]
_CONFORMANCE_LABELS = [
    ("A (acessível)", "A"),
    ("B (básica)", "B"),
    ("U (Unicode)", "U"),
]


class PDFAPage(QWidget):
    """Permite converter um PDF para uma aproximação de PDF/A (arquivamento) ou verificar
    se um PDF já atende a um subconjunto dos requisitos de PDF/A."""

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

        warning = QLabel(
            tr(
                "Conversão aproximada: remove JavaScript, anexos embutidos e criptografia, e "
                "declara conformidade PDF/A nos metadados — mas não embute perfil de cor "
                "(/OutputIntent) nem verifica fontes. Para arquivamento legal, valide o "
                "resultado com uma ferramenta dedicada (ex.: veraPDF) antes de considerar o "
                "documento arquivável."
            )
        )
        warning.setWordWrap(True)

        self.convert_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="pdfa"
        )

        self.convert_part_combo = QComboBox()
        self.convert_part_combo.addItems(_PARTS)
        self.convert_part_combo.setCurrentIndex(1)  # parte 2, o padrão mais comum

        self.convert_conformance_combo = QComboBox()
        for label, _value in _CONFORMANCE_LABELS:
            self.convert_conformance_combo.addItem(tr(label))
        self.convert_conformance_combo.setCurrentIndex(1)  # B, o nível mais permissivo

        apply_button = QPushButton(tr("Converter"))
        apply_button.clicked.connect(self._apply_convert)

        layout.addWidget(warning)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.convert_output_picker)
        layout.addWidget(QLabel(tr("Parte (PDF/A-N):")))
        layout.addWidget(self.convert_part_combo)
        layout.addWidget(QLabel(tr("Nível de conformidade:")))
        layout.addWidget(self.convert_conformance_combo)
        layout.addWidget(apply_button)
        return widget

    def _build_validate_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Verifica só um subconjunto dos requisitos de PDF/A (criptografia, "
                "JavaScript, anexos e metadados XMP) — não é validação ISO 19005 completa."
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

        part = int(_PARTS[self.convert_part_combo.currentIndex()])
        conformance = _CONFORMANCE_LABELS[self.convert_conformance_combo.currentIndex()][1]

        try:
            ConvertToPDFA().run(input_path, output_path, part=part, conformance=conformance)
        except Exception as exc:
            QMessageBox.critical(self, tr("PDF/A"), tr("Falha ao converter: {error}").format(error=exc))
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("PDF/A"), tr("PDF convertido com sucesso."))

    def _apply_validate(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("PDF/A"), tr("Abra um PDF para começar."))
            return

        try:
            result = ValidatePDFA().run(input_path)
        except Exception as exc:
            QMessageBox.critical(self, tr("PDF/A"), tr("Falha ao validar: {error}").format(error=exc))
            return

        if result.is_valid:
            QMessageBox.information(
                self, tr("PDF/A"), tr("Nenhum problema encontrado nas verificações realizadas.")
            )
        else:
            issues_text = "\n".join(f"• {issue}" for issue in result.issues)
            QMessageBox.warning(
                self,
                tr("PDF/A"),
                tr("Problemas encontrados:\n{issues}").format(issues=issues_text),
            )
