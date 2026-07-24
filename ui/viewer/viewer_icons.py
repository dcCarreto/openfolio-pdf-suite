"""Ícones da barra de ferramentas do visualizador, desenhados em runtime (mesma técnica
usada em ui/sidebar_icons.py e ui/flags.py)."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QIcon, QPolygonF

from ui.icon_utils import build_icon as _build


def build_open_icon() -> QIcon:
    def draw(p):
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(4, 6),
                    QPointF(9, 6),
                    QPointF(11, 8),
                    QPointF(18, 8),
                    QPointF(18, 17),
                    QPointF(4, 17),
                ]
            )
        )

    return _build(draw)


def build_prev_page_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(13, 4), QPointF(7, 11))
        p.drawLine(QPointF(7, 11), QPointF(13, 18))

    return _build(draw)


def build_next_page_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(9, 4), QPointF(15, 11))
        p.drawLine(QPointF(15, 11), QPointF(9, 18))

    return _build(draw)


def build_zoom_in_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QRectF(4, 4, 11, 11))
        p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 11.5))
        p.drawLine(QPointF(7, 9), QPointF(12, 9))
        p.drawLine(QPointF(13.2, 13.2), QPointF(18, 18))

    return _build(draw)


def build_zoom_out_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QRectF(4, 4, 11, 11))
        p.drawLine(QPointF(7, 9), QPointF(12, 9))
        p.drawLine(QPointF(13.2, 13.2), QPointF(18, 18))

    return _build(draw)


def build_fit_width_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(3, 11), QPointF(19, 11))
        p.drawLine(QPointF(3, 11), QPointF(7, 7))
        p.drawLine(QPointF(3, 11), QPointF(7, 15))
        p.drawLine(QPointF(19, 11), QPointF(15, 7))
        p.drawLine(QPointF(19, 11), QPointF(15, 15))

    return _build(draw)


def build_single_page_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(7, 3, 8, 16), 1.5, 1.5)

    return _build(draw)


def build_continuous_page_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(6, 2, 10, 8), 1.2, 1.2)
        p.drawRoundedRect(QRectF(6, 12, 10, 8), 1.2, 1.2)

    return _build(draw)


def build_thumbnails_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(3, 3, 7, 7), 1, 1)
        p.drawRoundedRect(QRectF(12, 3, 7, 7), 1, 1)
        p.drawRoundedRect(QRectF(3, 12, 7, 7), 1, 1)
        p.drawRoundedRect(QRectF(12, 12, 7, 7), 1, 1)

    return _build(draw)


def build_search_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QRectF(4, 4, 10, 10))
        p.drawLine(QPointF(12.5, 12.5), QPointF(18, 18))

    return _build(draw)
