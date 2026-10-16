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
    """Linha com campo de caminho somente-leitura e botão de busca.

    No modo "save" com `suggested_source`, o destino nunca fica "grudado" num arquivo de
    entrada antigo:

    - Sem escolha manual, o destino é um nome sugerido a partir da entrada atual
      (`contrato.pdf` -> `contrato_mesclado.pdf`), sempre de um arquivo que ainda não
      existe — nada é sobrescrito sem o usuário pedir.
    - Um caminho escolhido no diálogo (que já confirma a sobrescrita) vale para a entrada
      de quando foi escolhido. Se a entrada mudar, a escolha cai e a sugestão volta;
      antes, processar outro documento gravava por cima do resultado anterior sem aviso.
    """

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
        self._path_source: Optional[str] = None  # entrada para a qual `_path` foi escolhido
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

        # Se a sugestão vem da sessão do documento aberto, acompanha a troca de documento
        # na hora (com a página visível); nos demais casos, `showEvent` atualiza.
        owner = getattr(suggested_source, "__self__", None)
        session_signal = getattr(owner, "path_changed", None)
        if session_signal is not None and hasattr(session_signal, "connect"):
            session_signal.connect(self._refresh_display)
        self._refresh_display()

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
            self._path_source = self._current_source()
            self._refresh_display()
            self.path_changed.emit(path)

    def _current_source(self) -> Optional[str]:
        if self._suggested_source is None:
            return None
        try:
            return self._suggested_source() or None
        except Exception:
            return None

    def _suggestion(self, source: Optional[str]) -> str:
        if not source:
            return ""
        source_path = Path(source)
        extension = source_path.suffix or ".pdf"
        base = f"{source_path.stem}_{self._suggested_suffix}"
        candidate = source_path.with_name(f"{base}{extension}")
        counter = 2
        while candidate.exists():
            candidate = source_path.with_name(f"{base} ({counter}){extension}")
            counter += 1
        return str(candidate)

    def _suggested_start_path(self) -> str:
        if self._path:
            return self._path
        return self._suggestion(self._current_source())

    def path(self) -> str:
        if self._mode != "save" or self._suggested_source is None:
            return self._path
        source = self._current_source()
        if self._path and self._path_source is not None and self._path_source != source:
            self._path = ""  # escolhido para outro arquivo de entrada: não vale mais
            self._path_source = None
        return self._path or self._suggestion(source)

    def snapshot(self) -> tuple[str, Optional[str]]:
        """A escolha do usuário, para passar a outra instância (ver `ui/widget_state.py`)."""
        return self._path, self._path_source

    def restore(self, state: tuple[str, Optional[str]]) -> None:
        self._path, self._path_source = state
        self._refresh_display()

    def _refresh_display(self):
        current = self.path()
        self.path_edit.setText(current)
        self.path_edit.setToolTip(current)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_display()
