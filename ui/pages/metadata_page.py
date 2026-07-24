"""Aba de edição de metadados de PDFs."""

from PySide6.QtWidgets import QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.metadata import ReadMetadata, SetMetadata
from ui.i18n import tr
from ui.widgets.file_picker import FilePicker


class MetadataPage(QWidget):
    """Permite ler e editar os metadados (título, autor, assunto, palavras-chave) de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        self.input_picker.path_changed.connect(self._load)
        load_button = QPushButton(tr("Carregar metadados"))
        load_button.clicked.connect(self._load)

        self.title_edit = QLineEdit()
        self.author_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText(tr("Separadas por vírgula"))

        self.output_picker = FilePicker(mode="save")
        save_button = QPushButton(tr("Salvar"))
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.input_picker)
        layout.addWidget(load_button)
        layout.addWidget(QLabel(tr("Título:")))
        layout.addWidget(self.title_edit)
        layout.addWidget(QLabel(tr("Autor:")))
        layout.addWidget(self.author_edit)
        layout.addWidget(QLabel(tr("Assunto:")))
        layout.addWidget(self.subject_edit)
        layout.addWidget(QLabel(tr("Palavras-chave:")))
        layout.addWidget(self.keywords_edit)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

    def _load(self):
        input_path = self.input_picker.path()
        if not input_path:
            QMessageBox.warning(self, tr("Metadados"), tr("Escolha o arquivo de entrada."))
            return

        try:
            metadata = ReadMetadata().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Metadados"), tr("Falha ao ler metadados: {error}").format(error=exc)
            )
            return

        self.title_edit.setText(metadata["title"])
        self.author_edit.setText(metadata["author"])
        self.subject_edit.setText(metadata["subject"])
        self.keywords_edit.setText(metadata["keywords"])

    def _save(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, tr("Metadados"), tr("Escolha o arquivo de entrada."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Metadados"), tr("Escolha o arquivo de saída."))
            return

        try:
            SetMetadata().run(
                input_path,
                output_path,
                title=self.title_edit.text(),
                author=self.author_edit.text(),
                subject=self.subject_edit.text(),
                keywords=self.keywords_edit.text(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Metadados"), tr("Falha ao salvar metadados: {error}").format(error=exc)
            )
            return

        QMessageBox.information(self, tr("Metadados"), tr("Metadados salvos com sucesso."))
