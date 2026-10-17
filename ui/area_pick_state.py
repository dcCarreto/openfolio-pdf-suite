"""Estado compartilhado da marcação de áreas no visualizador (M04).

Antes, áreas e posições eram digitadas como coordenadas PDF: a área do texto novo, o
retângulo de um link, a posição e o tamanho de um campo de formulário, as margens de corte.
Isso exigia saber onde fica a origem da página e em que unidade ela é medida. Agora a aba
pede o visualizador e o usuário arrasta na página; a área chega à aba no espaço do usuário
do PDF (o mesmo de `/Rect` e das áreas de redação), e as áreas já marcadas aparecem
desenhadas.

Duas condições ligam a ferramenta: a aba estar visível (a janela informa com
`set_active_page`) e a aba querer áreas no modo em que está (`set_wanted`). Assim a
mesma instância serve a várias abas, e o arrasto vai só para a que está na tela.
"""

from PySide6.QtCore import QObject, Signal

Area = tuple[int, tuple[float, float, float, float]]  # (página, (left, bottom, right, top))


class AreaPickState(QObject):
    active_changed = Signal()
    areas_changed = Signal()
    area_picked = Signal(int, float, float, float, float)  # página, left, bottom, right, top

    def __init__(self):
        super().__init__()
        self._active_page = None
        self._wanted: set[int] = set()
        self._areas: dict[int, tuple[list[Area], int | None]] = {}

    # -- quem recebe a área ---------------------------------------------------------

    def set_active_page(self, page) -> None:
        """A aba visível no painel (ou None)."""
        self._update(lambda: setattr(self, "_active_page", page))

    def set_wanted(self, page, wanted: bool) -> None:
        """A aba quer (ou não) marcar áreas no modo em que está."""

        def change():
            key = id(page)
            if wanted:
                if key not in self._wanted and hasattr(page, "destroyed"):
                    # A troca de idioma recria as abas: a antiga não pode continuar na lista.
                    page.destroyed.connect(lambda *_args, key=key: self._forget(key))
                self._wanted.add(key)
            else:
                self._wanted.discard(key)

        self._update(change)

    def _forget(self, key: int) -> None:
        self._wanted.discard(key)
        self._areas.pop(key, None)

    def owner(self):
        """A aba que recebe o próximo arrasto (None se nenhuma)."""
        page = self._active_page
        return page if page is not None and id(page) in self._wanted else None

    def is_page_active(self) -> bool:
        return self.owner() is not None

    def pick(self, page_index: int, rect: tuple[float, float, float, float]) -> None:
        """Chamado pelo visualizador ao terminar de arrastar."""
        if self.is_page_active():
            self.area_picked.emit(page_index, *rect)

    # -- áreas desenhadas -----------------------------------------------------------

    def areas(self) -> list[Area]:
        owner = self.owner()
        return list(self._areas.get(id(owner), ([], None))[0]) if owner is not None else []

    def selected(self) -> int | None:
        owner = self.owner()
        return self._areas.get(id(owner), ([], None))[1] if owner is not None else None

    def set_areas(self, page, areas: list[Area], selected: int | None = None) -> None:
        """A aba informa as áreas que já marcou (e a selecionada), para o visualizador
        desenhar enquanto ela estiver na tela."""
        if self._areas.get(id(page)) == (list(areas), selected):
            return
        self._areas[id(page)] = (list(areas), selected)
        if page is self.owner():
            self.areas_changed.emit()

    def _update(self, change) -> None:
        before = self.owner()
        change()
        if self.owner() is not before:
            self.active_changed.emit()
            self.areas_changed.emit()
