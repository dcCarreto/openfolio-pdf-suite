"""Estado compartilhado do documento atualmente aberto no visualizador."""

from PySide6.QtCore import QObject, Signal


class DocumentSession(QObject):
    """Guarda o caminho do PDF atualmente aberto e notifica quem depende dele.

    Uma única instância vive em MainWindow e é compartilhada pelo visualizador e por
    todos os painéis de ferramenta: abrir um arquivo em qualquer lugar do app atualiza
    o visualizador e todas as ferramentas ao mesmo tempo.
    """

    path_changed = Signal()

    def __init__(self):
        super().__init__()
        self._path: str | None = None

    def path(self) -> str | None:
        return self._path

    def open(self, path: str) -> None:
        self._path = path
        self.path_changed.emit()

    def clear(self) -> None:
        self._path = None
        self.path_changed.emit()
