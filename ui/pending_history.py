"""Desfazer/refazer das marcações pendentes (anotações, áreas de redação) antes de gravá-las.

Guarda a lista inteira a cada mudança, então desenhar, apagar uma e "Limpar pendentes" se
desfazem do mesmo jeito. O Ctrl+Z da janela passa por aqui antes das versões do documento.
"""

from collections.abc import Callable


class PendingHistory:
    def __init__(self, state, restore: Callable[[list], None]):
        self._state = state
        self._restore = restore
        self._undo: list[list] = []
        self._redo: list[list] = []
        self._last = state.pending()
        self._replaying = False

    def changed(self) -> None:
        """Chamar a cada `pending_changed` do estado: guarda a lista de antes."""
        if not self._replaying:
            self._undo.append(self._last)
            self._redo.clear()
        self._last = self._state.pending()

    def reset(self) -> None:
        """O documento mudou: as listas guardadas eram de outro arquivo."""
        self._undo, self._redo = [], []
        self._last = self._state.pending()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._last)
            self._apply(self._undo.pop())

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._last)
            self._apply(self._redo.pop())

    def _apply(self, snapshot: list) -> None:
        self._replaying = True
        try:
            self._restore(snapshot)
        finally:
            self._replaying = False
