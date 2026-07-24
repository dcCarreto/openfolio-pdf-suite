"""Ícones de bandeira desenhados em runtime (sem depender de fonte de emoji).

Emojis de bandeira dependem do motor de texto combinar dois caracteres
"regional indicator" em um único glifo — suporte inconsistente entre
plataformas e até mesmo entre versões do Qt na mesma máquina. Desenhar a
bandeira como um ícone vetorial simples garante um resultado consistente.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF


def _blank_pixmap(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def build_us_flag_icon(width: int = 32, height: int = 20) -> QIcon:
    """Bandeira estilizada dos EUA: listras vermelhas/brancas e cantão azul."""
    pixmap = _blank_pixmap(width, height)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    stripe_count = 7
    stripe_height = height / stripe_count
    for index in range(stripe_count):
        color = QColor("#B22234") if index % 2 == 0 else QColor("#FFFFFF")
        painter.setBrush(color)
        painter.drawRect(QRectF(0, index * stripe_height, width, stripe_height + 0.5))

    canton_width = width * 0.42
    canton_height = stripe_height * 4
    painter.setBrush(QColor("#3C3B6E"))
    painter.drawRect(QRectF(0, 0, canton_width, canton_height))

    painter.end()
    return QIcon(pixmap)


def build_br_flag_icon(width: int = 32, height: int = 20) -> QIcon:
    """Bandeira estilizada do Brasil: fundo verde, losango amarelo, círculo azul."""
    pixmap = _blank_pixmap(width, height)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QColor("#009739"))
    painter.drawRect(QRectF(0, 0, width, height))

    center = QPointF(width / 2, height / 2)
    diamond = QPolygonF(
        [
            center + QPointF(0, -height * 0.46),
            center + QPointF(width * 0.46, 0),
            center + QPointF(0, height * 0.46),
            center + QPointF(-width * 0.46, 0),
        ]
    )
    painter.setBrush(QColor("#FEDD00"))
    painter.drawPolygon(diamond)

    radius = height * 0.24
    painter.setBrush(QColor("#012169"))
    painter.drawEllipse(center, radius, radius)

    painter.end()
    return QIcon(pixmap)
