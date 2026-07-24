"""Estado compartilhado da ferramenta de anotações: ferramenta/cor ativas e pendentes."""

from PySide6.QtCore import QObject, Signal

from core.annotations import AnnotationSpec

TOOLS = ("select", "highlight", "underline", "strikeout", "note", "ink", "stamp")

DEFAULT_COLOR = "ffeb3b"
DEFAULT_STAMP_TEXT = "APROVADO"


class AnnotationState(QObject):
    """Guarda a ferramenta/cor ativas e a lista de anotações ainda não salvas.

    Compartilhado entre o PdfViewer (que desenha e captura o mouse) e a AnnotationsPage
    (que escolhe a ferramenta/cor e grava o resultado); sobrevive à troca de idioma porque
    vive em MainWindow, assim como DocumentSession.
    """

    tool_changed = Signal()
    pending_changed = Signal()

    def __init__(self):
        super().__init__()
        self._active_tool: str | None = None
        self._active_color = DEFAULT_COLOR
        self._stamp_text = DEFAULT_STAMP_TEXT
        self._pending: list[AnnotationSpec] = []
        self._page_active = False

    def is_page_active(self) -> bool:
        """Se a aba de Anotações é a que está em primeiro plano na sidebar agora.

        Separado da ferramenta ativa de propósito: navegar para outra ferramenta não deve
        "esquecer" qual ferramenta de marcação estava selecionada, só deve parar de
        interceptar o mouse do visualizador até o usuário voltar para esta aba.
        """
        return self._page_active

    def set_page_active(self, active: bool) -> None:
        if active == self._page_active:
            return
        self._page_active = active
        self.tool_changed.emit()

    def active_tool(self) -> str | None:
        return self._active_tool

    def set_tool(self, tool: str | None) -> None:
        if tool is not None and tool not in TOOLS:
            raise ValueError(f"Ferramenta de anotação inválida: {tool}")
        if tool == self._active_tool:
            return
        self._active_tool = tool
        self.tool_changed.emit()

    def active_color(self) -> str:
        return self._active_color

    def set_color(self, color: str) -> None:
        self._active_color = color

    def stamp_text(self) -> str:
        return self._stamp_text

    def set_stamp_text(self, text: str) -> None:
        self._stamp_text = text

    def pending(self) -> list[AnnotationSpec]:
        return list(self._pending)

    def add_pending(self, spec: AnnotationSpec) -> None:
        self._pending.append(spec)
        self.pending_changed.emit()

    def remove_pending(self, spec: AnnotationSpec) -> None:
        self._pending.remove(spec)
        self.pending_changed.emit()

    def clear_pending(self) -> None:
        if not self._pending:
            return
        self._pending = []
        self.pending_changed.emit()
