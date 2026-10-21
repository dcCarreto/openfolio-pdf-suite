"""Widget reutilizável de seleção de arquivo ou diretório."""

import re
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget

from ui.i18n import tr
from ui.preferences import remember_folder_of, start_folder

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

    No modo "save" com a sessão do documento como `suggested_source` (`session.path`), a
    ferramenta altera o documento aberto:

    - Por padrão, o resultado é aplicado ao próprio documento, como um passo que Ctrl+Z
      desfaz (ver `ui/document_session.py`): `path()` devolve o caminho de uma versão nova
      do documento de trabalho, e a aba, ao chamar `session.open()` com ele, empilha o
      passo no histórico. Nenhum arquivo intermediário vai para a pasta do usuário.
    - "Procurar..." escolhe gravar o resultado em outro arquivo; o botão "No documento"
      volta ao padrão. `working_copy=False` desliga o padrão (ferramentas cujo resultado é
      um arquivo final, como proteger com senha ou assinar).

    Fora desse caso (ou em "salvar em outro arquivo"), o destino nunca fica "grudado" num
    arquivo de entrada antigo:

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
        working_copy: bool = True,
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

        owner = getattr(suggested_source, "__self__", None)
        self._session = owner if mode == "save" and hasattr(owner, "new_version_path") else None
        self._can_apply = self._session is not None and working_copy
        self._apply_to_document = self._can_apply

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(tr(_PLACEHOLDERS[mode]))
        browse_button = QPushButton(tr("Procurar..."))
        browse_button.setToolTip(tr(_TOOLTIPS[mode]))
        browse_button.clicked.connect(self._browse)
        self.document_button = QPushButton(tr("No documento"))
        self.document_button.setToolTip(tr("Aplicar o resultado ao documento aberto (Ctrl+Z desfaz)"))
        self.document_button.clicked.connect(self.use_document)
        self.document_button.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.path_edit)
        layout.addWidget(self.document_button)
        layout.addWidget(browse_button)

        # Se a sugestão vem da sessão do documento aberto, acompanha a troca de documento
        # na hora (com a página visível); nos demais casos, `showEvent` atualiza.
        session_signal = getattr(owner, "path_changed", None)
        if session_signal is not None and hasattr(session_signal, "connect"):
            session_signal.connect(self._refresh_display)
        self._refresh_display()

    def applies_to_document(self) -> bool:
        """Se o resultado vai para o documento aberto (e não para outro arquivo)."""
        return self._apply_to_document

    def use_document(self) -> None:
        if not self._can_apply:
            return
        self._apply_to_document = True
        self._path = ""
        self._path_source = None
        self._refresh_display()

    def _browse(self):
        if self._mode == "open":
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Selecionar arquivo"), start_folder(), self._file_filter
            )
        elif self._mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Salvar como"), start_folder(self._suggested_start_path()), self._file_filter
            )
        else:
            path = QFileDialog.getExistingDirectory(self, tr("Selecionar pasta"), start_folder())

        if path:
            remember_folder_of(path)
            self._path = path
            self._path_source = self._current_source()
            self._apply_to_document = False
            self._refresh_display()
            self.path_changed.emit(path)

    def _current_source(self) -> Optional[str]:
        if self._session is not None:
            return self._session.source_path() or None  # o arquivo do usuário, não a versão
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
        # A extensão é a do que vai ser gravado (o filtro), não a da entrada: converter
        # contrato.docx sugeria contrato_convertido.docx para um PDF.
        match = re.search(r"\*(\.\w+)", self._file_filter)
        extension = match.group(1) if match else source_path.suffix or ".pdf"
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

    def _file_path(self) -> str:
        if self._mode != "save" or (self._suggested_source is None and self._session is None):
            return self._path
        source = self._current_source()
        if self._path and self._path_source is not None and self._path_source != source:
            self._path = ""  # escolhido para outro arquivo de entrada: não vale mais
            self._path_source = None
        return self._path or self._suggestion(source)

    def path(self) -> str:
        if self._apply_to_document:
            # Uma versão nova do documento de trabalho; vazio sem documento aberto, para a
            # aba pedir que o usuário abra um PDF.
            return self._session.new_version_path() if self._session and self._session.path() else ""
        return self._file_path()

    def snapshot(self) -> tuple:
        """A escolha do usuário, para passar a outra instância (ver `ui/widget_state.py`)."""
        return self._path, self._path_source, self._apply_to_document

    def restore(self, state: tuple) -> None:
        self._path, self._path_source = state[0], state[1]
        if len(state) > 2 and self._can_apply:
            self._apply_to_document = state[2]
        elif self._path:
            self._apply_to_document = False
        self._refresh_display()

    def _refresh_display(self):
        if self._apply_to_document:
            text = tr("No documento aberto (Ctrl+Z desfaz)")
            self.path_edit.setText(text)
            self.path_edit.setToolTip(tr("O resultado é aplicado ao documento aberto. Use Arquivo > Salvar para gravar."))
        else:
            current = self._file_path()
            self.path_edit.setText(current)
            self.path_edit.setToolTip(current)
        self.document_button.setVisible(self._can_apply and not self._apply_to_document)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_display()
