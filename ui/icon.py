"""Ícone da aplicação, renderizado a partir do logo vetorial em assets/logo.svg."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
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
