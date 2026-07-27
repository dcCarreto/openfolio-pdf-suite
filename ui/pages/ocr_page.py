"""Aba de OCR: reconhecimento de texto em páginas de PDF que são só imagem (escaneadas)."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.ocr import OCRDocument, find_tesseract, get_available_languages
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_LANGUAGE_NAMES = {
    "eng": "Inglês",
    "por": "Português",
    "spa": "Espanhol",
    "fra": "Francês",
    "deu": "Alemão",
    "ita": "Italiano",
}


class OCRPage(QWidget):
    """Permite reconhecer texto em páginas escaneadas, tornando-as pesquisáveis."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.language_combo = QComboBox()
        self._languages = get_available_languages()
        for code in self._languages:
            self.language_combo.addItem(tr(_LANGUAGE_NAMES.get(code, code)), code)

        self.skip_pages_checkbox = QCheckBox(tr("Pular páginas que já têm texto"))
        self.skip_pages_checkbox.setChecked(True)

        self.tesseract_note = QLabel()
        self.tesseract_note.setWordWrap(True)
        self._update_tesseract_note()

        self.output_picker = FilePicker(
            mode="save", suggested_source=session.path, suggested_suffix="ocr"
        )
        self.apply_button = QPushButton(tr("Reconhecer texto"))
        self.apply_button.clicked.connect(self._apply)
        self.apply_button.setEnabled(find_tesseract() is not None and bool(self._languages))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Idioma do texto:")))
        layout.addWidget(self.language_combo)
        layout.addWidget(self.skip_pages_checkbox)
        layout.addWidget(self.tesseract_note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(self.apply_button)

    def _update_tesseract_note(self):
        if find_tesseract() is None:
            self.tesseract_note.setText(
                tr(
                    "Tesseract OCR não encontrado. Instale o Tesseract "
                    "(https://github.com/tesseract-ocr/tesseract) para usar esta ferramenta."
                )
            )
            self.language_combo.setEnabled(False)
        elif not self._languages:
            self.tesseract_note.setText(
                tr("Nenhum idioma de reconhecimento instalado no Tesseract.")
            )
            self.language_combo.setEnabled(False)
        else:
            self.tesseract_note.setText(
                tr("Tesseract encontrado. Idiomas disponíveis: {languages}.").format(
                    languages=", ".join(
                        tr(_LANGUAGE_NAMES.get(code, code)) for code in self._languages
                    )
                )
            )

    def _apply(self):
        input_path = self.session.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("OCR"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("OCR"), tr("Escolha o arquivo de saída."))
            return
        if self.language_combo.currentIndex() < 0:
            QMessageBox.warning(self, tr("OCR"), tr("Nenhum idioma de reconhecimento disponível."))
            return

        language = self.language_combo.currentData()

        try:
            pages_ocred = OCRDocument().run(
                input_path,
                output_path,
                language=language,
                skip_pages_with_text=self.skip_pages_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, tr("OCR"), tr("Falha ao reconhecer texto: {error}").format(error=exc))
            return

        self.session.open(output_path)
        if pages_ocred:
            QMessageBox.information(
                self,
                tr("OCR"),
                tr("Texto reconhecido em {count} página(s).").format(count=pages_ocred),
            )
        else:
            QMessageBox.information(
                self,
                tr("OCR"),
                tr("Nenhuma página precisou de OCR (o PDF já tinha texto)."),
            )
