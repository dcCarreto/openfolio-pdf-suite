"""Aba de edição de metadados de PDFs."""

from PySide6.QtWidgets import QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.metadata import ReadMetadata, SetMetadata
from ui.widgets.file_picker import FilePicker


class MetadataPage(QWidget):
    """Permite ler e editar os metadados (título, autor, assunto, palavras-chave) de um PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_picker = FilePicker(mode="open")
        load_button = QPushButton("Carregar metadados")
        load_button.clicked.connect(self._load)

        self.title_edit = QLineEdit()
        self.author_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("Separadas por vírgula")

        self.output_picker = FilePicker(mode="save")
        save_button = QPushButton("Salvar")
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arquivo PDF de entrada:"))
        layout.addWidget(self.input_picker)
        layout.addWidget(load_button)
        layout.addWidget(QLabel("Título:"))
        layout.addWidget(self.title_edit)
        layout.addWidget(QLabel("Autor:"))
        layout.addWidget(self.author_edit)
        layout.addWidget(QLabel("Assunto:"))
        layout.addWidget(self.subject_edit)
        layout.addWidget(QLabel("Palavras-chave:"))
        layout.addWidget(self.keywords_edit)
        layout.addWidget(QLabel("Arquivo de saída:"))
        layout.addWidget(self.output_picker)
        layout.addWidget(save_button)

    def _load(self):
        input_path = self.input_picker.path()
        if not input_path:
            QMessageBox.warning(self, "Metadados", "Escolha o arquivo de entrada.")
            return

        try:
            metadata = ReadMetadata().run(input_path)
        except Exception as exc:
            QMessageBox.critical(self, "Metadados", f"Falha ao ler metadados: {exc}")
            return

        self.title_edit.setText(metadata["title"])
        self.author_edit.setText(metadata["author"])
        self.subject_edit.setText(metadata["subject"])
        self.keywords_edit.setText(metadata["keywords"])

    def _save(self):
        input_path = self.input_picker.path()
        output_path = self.output_picker.path()

        if not input_path:
            QMessageBox.warning(self, "Metadados", "Escolha o arquivo de entrada.")
            return
        if not output_path:
            QMessageBox.warning(self, "Metadados", "Escolha o arquivo de saída.")
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
            QMessageBox.critical(self, "Metadados", f"Falha ao salvar metadados: {exc}")
            return

        QMessageBox.information(self, "Metadados", "Metadados salvos com sucesso.")
