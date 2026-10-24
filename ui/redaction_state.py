"""Estado compartilhado da ferramenta de redação: retângulos pendentes a apagar.

Espelha ui/annotation_state.py, mas mais simples: não há "ferramenta" para escolher —
arrastar no visualizador sempre marca um retângulo simples (sem hit-test de texto).
Redação é destrutiva por natureza, então fica deliberadamente separada do estado de
anotações (que é reversível/aditivo) em vez de reaproveitar o mesmo objeto.

As áreas pendentes são revisáveis uma a uma antes de aplicar: o painel lista cada uma, a
selecionada aparece destacada no visualizador e pode ser removida sozinha. Áreas idênticas
(ex.: rodar a detecção automática duas vezes) não se repetem na lista.
"""

from PySide6.QtCore import QObject, Signal

from core.redaction import RedactionRect


class RedactionState(QObject):
    pending_changed = Signal()
    active_changed = Signal()
    selection_changed = Signal()

    def __init__(self):
        super().__init__()
        self._page_active = False
        self._pending: list[RedactionRect] = []
        self._selected: RedactionRect | None = None

    def is_page_active(self) -> bool:
        return self._page_active

    def set_page_active(self, active: bool) -> None:
        if active == self._page_active:
            return
        self._page_active = active
        self.active_changed.emit()

    def pending(self) -> list[RedactionRect]:
        return list(self._pending)

    def add_pending(self, rect: RedactionRect) -> bool:
        """Adiciona a área; devolve False (sem emitir sinal) se ela já estava na lista."""
        return self.add_many([rect]) == 1

    def add_many(self, rects: list[RedactionRect]) -> int:
        """Adiciona várias áreas de uma vez, ignorando as repetidas; devolve quantas entraram."""
        added = 0
        for rect in rects:
            if rect not in self._pending:
                self._pending.append(rect)
                added += 1
        if added:
            self.pending_changed.emit()
        return added

    def remove_pending(self, rect: RedactionRect) -> None:
        self.remove_many([rect])

    def remove_many(self, rects: list[RedactionRect]) -> None:
        remaining = [rect for rect in self._pending if rect not in rects]
        if len(remaining) == len(self._pending):
            return
        self._pending = remaining
        if self._selected is not None and self._selected not in self._pending:
            self._selected = None
            self.selection_changed.emit()
        self.pending_changed.emit()

    def clear_pending(self) -> None:
        if not self._pending:
            return
        self._pending = []
        if self._selected is not None:
            self._selected = None
            self.selection_changed.emit()
        self.pending_changed.emit()

    def set_pending(self, rects: list[RedactionRect]) -> None:
        """Troca a lista inteira (desfazer/refazer)."""
        self._pending = list(rects)
        if self._selected is not None and self._selected not in self._pending:
            self._selected = None
            self.selection_changed.emit()
        self.pending_changed.emit()

    def selected(self) -> RedactionRect | None:
        return self._selected

    def set_selected(self, rect: RedactionRect | None) -> None:
        if rect is not None and rect not in self._pending:
            rect = None
        if rect == self._selected:
            return
        self._selected = rect
        self.selection_changed.emit()
