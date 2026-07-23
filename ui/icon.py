"""Ícone da aplicação, desenhado em runtime (sem depender de arquivos externos)."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def build_app_icon() -> QIcon:
    """Gera o ícone do OpenFolio PDF Suite: um quadrado arredondado com o monograma 'OF'."""
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#0a84ff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)

    painter.setPen(QColor("#f5f5f7"))
    painter.setFont(QFont("Segoe UI", 92, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "OF")

    painter.end()
    return QIcon(pixmap)
