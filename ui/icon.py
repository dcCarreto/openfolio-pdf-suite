"""Ícone da aplicação, renderizado a partir do logo vetorial em assets/logo.svg."""

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.svg"
_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def build_app_icon() -> QIcon:
    """Monta o QIcon do OpenFolio PDF Suite em várias resoluções, a partir do SVG do logo."""
    renderer = QSvgRenderer(str(_LOGO_PATH))
    icon = QIcon()

    for size in _ICON_SIZES:
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)

    return icon


LOGO_PLATE = "#283040"  # a placa grafite do logo da faixa do topo: cor da marca, fora dos tokens


def build_logo_tile() -> QIcon:
    """O logo da faixa do topo: a placa grafite de 30 x 30 (raio 9) com o ícone real do app,
    de 20 x 20, no meio. Em 1x e 2x, nítido em telas de alta densidade."""
    renderer = QSvgRenderer(str(_LOGO_PATH))
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(QSize(30 * scale, 30 * scale))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(LOGO_PLATE))
        painter.drawRoundedRect(QRectF(0, 0, 30, 30), 9, 9)
        renderer.render(painter, QRectF(5, 5, 20, 20))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    return icon
