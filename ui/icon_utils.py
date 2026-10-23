"""Helper compartilhado para desenhar ícones vetoriais via QPainter.

Emoji dependem de uma fonte de emoji instalada no sistema para renderizar
corretamente - suporte inconsistente entre plataformas (o bug das bandeiras
veio exatamente disso). Desenhar cada ícone como um glifo vetorial simples
garante o mesmo visual em qualquer sistema operacional.

O traço usa a cor do texto do tema na hora de pintar (A14): trocar entre o tema
escuro e o claro não exige recriar os ícones já postos em botões e listas.
"""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPen, QPixmap

DEFAULT_SIZE = 22


class _ThemedIconEngine(QIconEngine):
    def __init__(self, draw, size: int):
        super().__init__()
        self._draw = draw
        self._size = size

    def _color(self, mode: QIcon.Mode) -> QColor:
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Normal
        return QGuiApplication.palette().color(group, QPalette.ColorRole.WindowText)

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(rect.topLeft())
        painter.scale(rect.width() / self._size, rect.height() / self._size)
        pen = QPen(self._color(mode))
        pen.setWidthF(1.6)
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
        return _ThemedIconEngine(self._draw, self._size)


def build_icon(draw, size: int = DEFAULT_SIZE) -> QIcon:
    """`draw(painter)` desenha num quadro de `size` x `size`, com a caneta já na cor do tema."""
    return QIcon(_ThemedIconEngine(draw, size))
