"""Helper compartilhado para desenhar ícones vetoriais via QPainter.

Emoji dependem de uma fonte de emoji instalada no sistema para renderizar
corretamente - suporte inconsistente entre plataformas (o bug das bandeiras
veio exatamente disso). Desenhar cada ícone como um glifo vetorial simples
garante o mesmo visual em qualquer sistema operacional.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

DEFAULT_COLOR = "#e8e8ed"
DEFAULT_SIZE = 22


def build_icon(draw, size: int = DEFAULT_SIZE, color: str = DEFAULT_COLOR) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    draw(painter)

    painter.end()
    return QIcon(pixmap)
