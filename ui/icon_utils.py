"""Helper compartilhado para desenhar ícones vetoriais via QPainter.

Emoji dependem de uma fonte de emoji instalada no sistema para renderizar
corretamente - suporte inconsistente entre plataformas (o bug das bandeiras
veio exatamente disso). Desenhar cada ícone como um glifo vetorial simples
garante o mesmo visual em qualquer sistema operacional.

O traço usa a cor do tema e do estado na hora de pintar (`ui.theme.icon_color`): trocar
entre o tema escuro e o claro não exige recriar os ícones já postos em botões e listas.
"""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPen, QPixmap

from ui.theme import icon_color

DEFAULT_SIZE = 24  # a grade em que os ícones são desenhados
STROKE = 1.5  # o traço na grade de 24
MIN_STROKE_PX = 1.25  # num ícone pequeno, o traço não fica mais fino que isso na tela


class _ThemedIconEngine(QIconEngine):
    def __init__(self, draw, size: int, color=None):
        super().__init__()
        self._draw = draw
        self._size = size
        self._color = color  # fixa (sucesso, erro); sem ela, a do tema e do estado

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(rect.topLeft())
        painter.scale(rect.width() / self._size, rect.height() / self._size)
        pen = QPen(self._color if self._color is not None else icon_color(mode, state))
        # Na grade de 24: 1,5; num ícone pequeno (18 px), engrossa para não passar de 1,25 px.
        scale = min(rect.width(), rect.height()) / self._size or 1
        pen.setWidthF(max(STROKE, MIN_STROKE_PX / scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        self._draw(painter)
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pixmap

    def clone(self) -> QIconEngine:
        return _ThemedIconEngine(self._draw, self._size, self._color)


def build_icon(draw, size: int = DEFAULT_SIZE, color=None) -> QIcon:
    """`draw(painter)` desenha num quadro de `size` x `size`, com a caneta já na cor do tema
    (ou em `color`, para os estados de sucesso e erro)."""
    return QIcon(_ThemedIconEngine(draw, size, color))


def filled(painter: QPainter) -> None:
    """Preenche as próximas formas com a cor do traço (check-circle, pontos, alfinete)."""
    painter.setBrush(painter.pen().color())


def hollow(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
