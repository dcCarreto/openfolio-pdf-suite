"""Widget reutilizável de seleção de arquivo ou diretório."""

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class FilePicker(QWidget):
    """Linha com campo de caminho somente-leitura e botão de busca."""

    def __init__(self, mode: str = "open", file_filter: str = "PDF (*.pdf)", parent=None):
        super().__init__(parent)
        if mode not in ("open", "save", "directory"):
            raise ValueError(f"Modo inválido: {mode}")
        self._mode = mode
        self._file_filter = file_filter
        self._path = ""

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        browse_button = QPushButton("Procurar...")
        browse_button.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.path_edit)
        layout.addWidget(browse_button)

    def _browse(self):
        if self._mode == "open":
            path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo", "", self._file_filter)
        elif self._mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "Salvar como", "", self._file_filter)
        else:
            path = QFileDialog.getExistingDirectory(self, "Selecionar pasta")

        if path:
            self._path = path
            self.path_edit.setText(path)

    def path(self) -> str:
        return self._path
