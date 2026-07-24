"""Estado compartilhado da ferramenta de redação: retângulos pendentes a apagar.

Espelha ui/annotation_state.py, mas mais simples: não há "ferramenta" para escolher —
arrastar no visualizador sempre marca um retângulo simples (sem hit-test de texto).
Redação é destrutiva por natureza, então fica deliberadamente separada do estado de
anotações (que é reversível/aditivo) em vez de reaproveitar o mesmo objeto.
"""

from PySide6.QtCore import QObject, Signal

from core.redaction import RedactionRect


class RedactionState(QObject):
    pending_changed = Signal()
    active_changed = Signal()

    def __init__(self):
        super().__init__()
        self._page_active = False
        self._pending: list[RedactionRect] = []

    def is_page_active(self) -> bool:
        return self._page_active

    def set_page_active(self, active: bool) -> None:
        if active == self._page_active:
            return
        self._page_active = active
        self.active_changed.emit()

    def pending(self) -> list[RedactionRect]:
        return list(self._pending)

    def add_pending(self, rect: RedactionRect) -> None:
        self._pending.append(rect)
        self.pending_changed.emit()

    def remove_pending(self, rect: RedactionRect) -> None:
        self._pending.remove(rect)
        self.pending_changed.emit()

    def clear_pending(self) -> None:
        if not self._pending:
            return
        self._pending = []
        self.pending_changed.emit()
