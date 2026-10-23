"""Estado compartilhado da ferramenta de medição: unidade ativa e última medição feita.

Espelha `ui/redaction_state.py` na forma (estado `page_active` + sinais Qt), mas não guarda
uma lista de "pendentes": medir não produz nenhuma alteração no PDF, só um resultado
informativo (distância entre dois pontos clicados no visualizador), então basta lembrar o
último segmento medido para redesenhá-lo entre re-renderizações da página (zoom, troca de
página etc.).
"""

from PySide6.QtCore import QObject, Signal

UNITS = ("mm", "cm", "in", "pt")
DEFAULT_UNIT = "mm"

_POINTS_PER_UNIT = {
    "pt": 1.0,
    "in": 72.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
}


def convert_points(value_pt: float, unit: str) -> float:
    """Converte uma distância em pontos PDF (1/72 polegada) para a unidade pedida.

    Assume o `/UserUnit` padrão de 1.0 (1 ponto = 1/72 polegada) — PDFs de engenharia que
    declaram um `/UserUnit` diferente não são detectados aqui; a medição continuaria
    correta em pontos, só a conversão para mm/cm/in ficaria proporcionalmente errada.
    """
    if unit not in _POINTS_PER_UNIT:
        raise ValueError(f"Unidade inválida: {unit}")
    return value_pt / _POINTS_PER_UNIT[unit]


def format_distance(value_pt: float, unit: str) -> str:
    return f"{convert_points(value_pt, unit):.2f} {unit}"


class MeasureState(QObject):
    active_changed = Signal()
    result_changed = Signal()
    unit_changed = Signal()

    def __init__(self):
        super().__init__()
        self._page_active = False
        self._unit = DEFAULT_UNIT
        self._last_segment: tuple[int, tuple[float, float], tuple[float, float]] | None = None
        self._last_distance_pt: float | None = None

    def is_page_active(self) -> bool:
        return self._page_active

    def set_page_active(self, active: bool) -> None:
        if active == self._page_active:
            return
        self._page_active = active
        self.active_changed.emit()

    def unit(self) -> str:
        return self._unit

    def set_unit(self, unit: str) -> None:
        if unit not in UNITS:
            raise ValueError(f"Unidade inválida: {unit}")
        if unit == self._unit:
            return
        self._unit = unit
        self.unit_changed.emit()

    def last_segment(self):
        return self._last_segment

    def last_distance_pt(self) -> float | None:
        return self._last_distance_pt

    def set_result(
        self, page_index: int, start_pdf: tuple[float, float], end_pdf: tuple[float, float]
    ) -> None:
        self._last_segment = (page_index, start_pdf, end_pdf)
        dx = end_pdf[0] - start_pdf[0]
        dy = end_pdf[1] - start_pdf[1]
        self._last_distance_pt = (dx**2 + dy**2) ** 0.5
        self.result_changed.emit()

    def clear_result(self) -> None:
        if self._last_segment is None:
            return
        self._last_segment = None
        self._last_distance_pt = None
        self.result_changed.emit()
