"""Widget reutilizável de seleção de arquivo ou diretório."""

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget

from ui.i18n import tr

_PLACEHOLDERS = {
    "open": "Nenhum arquivo selecionado",
    "save": "Nenhum destino selecionado",
    "directory": "Nenhuma pasta selecionada",
}

_TOOLTIPS = {
    "open": "Escolher arquivo",
    "save": "Escolher onde salvar",
    "directory": "Escolher pasta",
}


class FilePicker(QWidget):
    """Linha com campo de caminho somente-leitura e botão de busca."""

    path_changed = Signal(str)

    def __init__(
        self,
        mode: str = "open",
        file_filter: str = "PDF (*.pdf)",
        parent=None,
        suggested_source: Optional[Callable[[], Optional[str]]] = None,
        suggested_suffix: str = "editado",
    ):
        super().__init__(parent)
        if mode not in ("open", "save", "directory"):
            raise ValueError(f"Modo inválido: {mode}")
        self._mode = mode
        self._file_filter = file_filter
        self._path = ""
        # Usado só no modo "save": sugere um nome de saída baseado no arquivo de entrada
        # (ex.: contrato.pdf -> contrato_mesclado.pdf) em vez de deixar o campo vazio.
        self._suggested_source = suggested_source
        self._suggested_suffix = suggested_suffix

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(tr(_PLACEHOLDERS[mode]))
        browse_button = QPushButton(tr("Procurar..."))
        browse_button.setToolTip(tr(_TOOLTIPS[mode]))
        browse_button.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.path_edit)
        layout.addWidget(browse_button)

    def _browse(self):
        if self._mode == "open":
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Selecionar arquivo"), "", self._file_filter
            )
        elif self._mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Salvar como"), self._suggested_start_path(), self._file_filter
            )
        else:
            path = QFileDialog.getExistingDirectory(self, tr("Selecionar pasta"))

        if path:
            self._path = path
            self.path_edit.setText(path)
            self.path_changed.emit(path)

    def _suggested_start_path(self) -> str:
        if self._path:
            return self._path
        if self._suggested_source is None:
            return ""
        try:
            source_path = self._suggested_source()
        except Exception:
            return ""
        if not source_path:
            return ""
        source = Path(source_path)
        return str(source.with_name(f"{source.stem}_{self._suggested_suffix}{source.suffix or '.pdf'}"))

    def path(self) -> str:
        return self._path
