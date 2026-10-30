"""Aba de OCR: reconhecimento de texto em páginas de PDF que são só imagem (escaneadas)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.ocr import DEFAULT_DPI, OCRDocument, find_tesseract, get_available_languages, has_orientation_data
from ui.i18n import PT_BR, get_language, plural, tr
from ui.tasks import call_with_progress, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_info, notify_success

_LANGUAGE_NAMES = {
    "eng": "Inglês",
    "por": "Português",
    "spa": "Espanhol",
    "fra": "Francês",
    "deu": "Alemão",
    "ita": "Italiano",
}
_MODES = [
    ("auto", "Só as escaneadas"),
    ("force", "Todas (forçar OCR)"),
    ("redo", "Refazer o OCR (tira o texto reconhecido antes)"),
]


def natural_list(items: list[str]) -> str:
    """"português e inglês", "a, b e c" ("a, b and c" em inglês)."""
    if len(items) < 2:
        return "".join(items)
    return tr("{items} e {last}").format(items=", ".join(items[:-1]), last=items[-1])


# Os instaladores do app trazem o motor de OCR; isto só aparece rodando do código-fonte. O nome
# dele e os comandos ficam no README, e não na interface.
_INSTALL_HELP = (
    "Os instaladores do app já trazem o reconhecimento de texto. Rodando do código-fonte, ele "
    'precisa ser instalado à parte: os passos estão no README, em "Requisitos". Depois, reabra o app.'
)


class OCRPage(QWidget):
    """Permite reconhecer texto em páginas escaneadas, tornando-as pesquisáveis."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self._tesseract = find_tesseract()
        self._languages = get_available_languages()
        self.language_list = QListWidget()
        self.language_list.setMaximumHeight(110)
        for code in self._languages:
            item = QListWidgetItem(tr(_LANGUAGE_NAMES.get(code, code)))
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code == self._default_language() else Qt.CheckState.Unchecked)
            self.language_list.addItem(item)

        self.mode_combo = QComboBox()
        for mode, label in _MODES:
            self.mode_combo.addItem(tr(label), mode)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(150, 600)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setValue(DEFAULT_DPI)
        self.dpi_spin.setToolTip(tr("Resolução usada para ler a página. Texto pequeno pede mais DPI; 300 serve para a maioria."))

        self.orientation_checkbox = QCheckBox(tr("Corrigir páginas digitalizadas de lado"))
        self.orientation_checkbox.setToolTip(tr("Detecta páginas digitalizadas de lado ou de cabeça para baixo."))
        if self._tesseract and has_orientation_data():
            self.orientation_checkbox.setChecked(True)
        else:
            self.orientation_checkbox.setEnabled(False)
            self.orientation_checkbox.setToolTip(tr("Requer a detecção de orientação do reconhecimento de texto."))

        self.straighten_checkbox = QCheckBox(tr("Endireitar as páginas no documento"))
        self.straighten_checkbox.setToolTip(
            tr(
                "Gira as páginas tortas (até 5°) e põe de pé as digitalizadas de lado, como a aba "
                "Limpar escaneados. Sem isso, o OCR lê na orientação certa, mas a página fica como está."
            )
        )

        self.tesseract_note = QLabel()
        self.tesseract_note.setWordWrap(True)
        self.tesseract_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._update_tesseract_note()

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="ocr"
        )
        self.apply_button = QPushButton(tr("Reconhecer texto"))
        self.action_buttons.append(self.apply_button)
        self.apply_button.clicked.connect(self._apply)
        self.apply_button.setEnabled(self._tesseract is not None and bool(self._languages))

        options = QFormLayout()
        options.addRow(tr("Páginas:"), self.mode_combo)
        options.addRow(tr("DPI:"), self.dpi_spin)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        languages_label = QLabel(tr("Idiomas do texto (marque todos os que aparecem no documento):"))
        languages_label.setWordWrap(True)
        layout.addWidget(languages_label)
        layout.addWidget(self.language_list)
        layout.addLayout(options)
        layout.addWidget(self.orientation_checkbox)
        layout.addWidget(self.straighten_checkbox)
        layout.addWidget(self.tesseract_note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(self.apply_button)

    def _default_language(self) -> str | None:
        for code in ("por", "eng"):
            if code in self._languages:
                return code
        return self._languages[0] if self._languages else None

    def selected_languages(self) -> list[str]:
        codes = []
        for row in range(self.language_list.count()):
            item = self.language_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                codes.append(item.data(Qt.ItemDataRole.UserRole))
        return codes

    def _update_tesseract_note(self):
        if self._tesseract is None:
            self.tesseract_note.setText(tr("O reconhecimento de texto não está instalado neste computador.") + " " + tr(_INSTALL_HELP))
            self.language_list.setEnabled(False)
        elif not self._languages:
            self.tesseract_note.setText(
                tr("Nenhum idioma de reconhecimento instalado.") + " " + tr(_INSTALL_HELP)
            )
            self.language_list.setEnabled(False)
        else:
            # "Idiomas disponíveis: português e inglês." (em português, os nomes em minúscula)
            names = [tr(_LANGUAGE_NAMES.get(code, code)) for code in sorted(self._languages, key=lambda c: c != "por")]
            if get_language() == PT_BR:
                names = [name.lower() for name in names]
            note = tr("Idiomas disponíveis: {languages}.").format(languages=natural_list(names))
            if "por" not in self._languages:
                note += " " + tr("Para reconhecer português, instale o idioma português do reconhecimento de texto.")
            self.tesseract_note.setText(note)

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            notify_error(self, tr("OCR"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("OCR"), tr("Escolha o arquivo de saída."))
            return
        languages = self.selected_languages()
        if not languages:
            notify_error(self, tr("OCR"), tr("Marque pelo menos um idioma do texto."))
            return

        task = call_with_progress(
            OCRDocument().run,
            input_path,
            output_path,
            language="+".join(languages),
            mode=self.mode_combo.currentData(),
            dpi=self.dpi_spin.value(),
            detect_orientation=self.orientation_checkbox.isChecked(),
            straighten=self.straighten_checkbox.isChecked(),
        )

        def done(pages_ocred):
            self.session.open(output_path)
            if pages_ocred:
                notify_success(
                    self,
                    tr("OCR"),
                    plural(pages_ocred, "Texto reconhecido em 1 página.", "Texto reconhecido em {count} páginas."),
                )
            else:
                notify_info(
                    self,
                    tr("OCR"),
                    tr("Nenhuma página precisou de OCR (o PDF já tinha texto)."),
                )

        run_task(
            self,
            tr("OCR"),
            task,
            on_success=done,
            error_message=tr("Falha ao reconhecer texto: {error}"),
        )
