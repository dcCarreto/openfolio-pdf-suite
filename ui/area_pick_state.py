"""Estado compartilhado da marcação de áreas no visualizador para a edição de texto.

Antes, a área a cobrir e reescrever era digitada como coordenadas PDF numa tabela, o que
exigia saber onde fica a origem da página e em que unidade ela é medida. Agora, com a aba
Editar no modo "Editar texto", arrastar no visualizador marca a área (no espaço do usuário
do PDF, como as áreas de redação), e as áreas já marcadas aparecem desenhadas na página.

A ferramenta só fica ativa com as duas condições: a aba Editar visível (a janela informa,
`set_page_active`) e o modo "Editar texto" escolhido nela (`set_mode_active`).
"""

from PySide6.QtCore import QObject, Signal

Area = tuple[int, tuple[float, float, float, float]]  # (página, (left, bottom, right, top))


class AreaPickState(QObject):
    active_changed = Signal()
    areas_changed = Signal()
    area_picked = Signal(int, float, float, float, float)  # página, left, bottom, right, top

    def __init__(self):
        super().__init__()
        self._page_active = False
        self._mode_active = False
        self._areas: list[Area] = []
        self._selected: int | None = None

    def is_page_active(self) -> bool:
        return self._page_active and self._mode_active

    def set_page_active(self, active: bool) -> None:
        self._set(page=active)

    def set_mode_active(self, active: bool) -> None:
        self._set(mode=active)

    def _set(self, page: bool | None = None, mode: bool | None = None) -> None:
        before = self.is_page_active()
        if page is not None:
            self._page_active = page
        if mode is not None:
            self._mode_active = mode
        if self.is_page_active() != before:
            self.active_changed.emit()

    def pick(self, page_index: int, rect: tuple[float, float, float, float]) -> None:
        """Chamado pelo visualizador ao terminar de arrastar."""
        self.area_picked.emit(page_index, *rect)

    def areas(self) -> list[Area]:
        return list(self._areas)

    def selected(self) -> int | None:
        return self._selected

    def set_areas(self, areas: list[Area], selected: int | None = None) -> None:
        """A aba informa as áreas da tabela (e a selecionada), para o visualizador desenhar."""
        if areas == self._areas and selected == self._selected:
            return
        self._areas = list(areas)
        self._selected = selected
        self.areas_changed.emit()
