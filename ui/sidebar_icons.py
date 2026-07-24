"""Ícones da barra lateral, desenhados em runtime (mesma técnica do logo/bandeiras).

Emoji dependem de uma fonte de emoji instalada no sistema para renderizar
corretamente - suporte inconsistente entre plataformas (o bug das bandeiras
veio exatamente disso). Desenhar cada ícone como um glifo vetorial simples
garante o mesmo visual em qualquer sistema operacional.
"""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPolygonF

from ui.icon_utils import DEFAULT_COLOR as _COLOR
from ui.icon_utils import build_icon as _build


def build_create_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(5, 3, 12, 16), 2, 2)
        p.drawLine(QPointF(11, 8), QPointF(11, 14))
        p.drawLine(QPointF(8, 11), QPointF(14, 11))

    return _build(draw)


def build_merge_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(8, 5, 10, 13), 2, 2)
        p.drawRoundedRect(QRectF(4, 8, 10, 13), 2, 2)

    return _build(draw)


def build_split_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(6, 5), QPointF(16, 17))
        p.drawLine(QPointF(16, 5), QPointF(6, 17))
        p.drawEllipse(QPointF(6, 17), 1.6, 1.6)
        p.drawEllipse(QPointF(16, 17), 1.6, 1.6)

    return _build(draw)


def build_pages_icon() -> QIcon:
    def draw(p):
        p.drawArc(QRectF(5, 5, 12, 12), 20 * 16, 300 * 16)
        p.setBrush(QColor(_COLOR))
        p.drawPolygon(
            QPolygonF([QPointF(14.6, 6.0), QPointF(17.4, 6.8), QPointF(15.4, 9.2)])
        )

    return _build(draw)


def build_compress_icon() -> QIcon:
    def draw(p):
        # seta de cima apontando para baixo
        p.drawLine(QPointF(11, 3), QPointF(11, 8))
        p.drawLine(QPointF(7.5, 5.5), QPointF(11, 9))
        p.drawLine(QPointF(14.5, 5.5), QPointF(11, 9))
        # seta de baixo apontando para cima
        p.drawLine(QPointF(11, 19), QPointF(11, 14))
        p.drawLine(QPointF(7.5, 16.5), QPointF(11, 13))
        p.drawLine(QPointF(14.5, 16.5), QPointF(11, 13))

    return _build(draw)


def build_convert_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(5, 8), QPointF(15, 8))
        p.drawLine(QPointF(12, 5), QPointF(15, 8))
        p.drawLine(QPointF(12, 11), QPointF(15, 8))
        p.drawLine(QPointF(17, 14), QPointF(7, 14))
        p.drawLine(QPointF(10, 11), QPointF(7, 14))
        p.drawLine(QPointF(10, 17), QPointF(7, 14))

    return _build(draw)


def build_watermark_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QRectF(6, 9, 10, 9))
        p.drawPolyline(QPolygonF([QPointF(7.5, 11), QPointF(11, 4), QPointF(14.5, 11)]))

    return _build(draw)


def build_protect_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(6, 10, 10, 8), 1.5, 1.5)
        p.drawArc(QRectF(7.5, 4, 7, 9), 0, 180 * 16)

    return _build(draw)


def build_metadata_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QRectF(4, 4, 14, 14))
        p.drawLine(QPointF(11, 10), QPointF(11, 15))
        p.setBrush(QColor(_COLOR))
        p.drawEllipse(QPointF(11, 7.2), 1.1, 1.1)

    return _build(draw)


def build_page_numbers_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(8, 5), QPointF(6, 17))
        p.drawLine(QPointF(14, 5), QPointF(12, 17))
        p.drawLine(QPointF(5, 9), QPointF(16, 9))
        p.drawLine(QPointF(5, 14), QPointF(16, 14))

    return _build(draw)


def build_extract_text_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(4, 3, 10, 14), 1.5, 1.5)
        p.drawLine(QPointF(6.5, 7), QPointF(11.5, 7))
        p.drawLine(QPointF(6.5, 10), QPointF(11.5, 10))
        p.drawLine(QPointF(6.5, 13), QPointF(9.5, 13))
        p.drawLine(QPointF(13, 13), QPointF(18, 18))
        p.drawLine(QPointF(14.5, 18), QPointF(18, 18))
        p.drawLine(QPointF(18, 14.5), QPointF(18, 18))

    return _build(draw)


def build_extract_images_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(4, 5, 14, 12), 1.5, 1.5)
        p.drawEllipse(QPointF(9, 9), 1.4, 1.4)
        p.drawPolyline(
            QPolygonF(
                [
                    QPointF(5, 16),
                    QPointF(10, 10),
                    QPointF(13, 13),
                    QPointF(15, 11),
                    QPointF(18, 16),
                ]
            )
        )

    return _build(draw)


def build_crop_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(7, 4), QPointF(7, 15))
        p.drawLine(QPointF(7, 15), QPointF(18, 15))
        p.drawLine(QPointF(15, 7), QPointF(4, 7))
        p.drawLine(QPointF(15, 7), QPointF(15, 18))

    return _build(draw)


def build_bookmarks_icon() -> QIcon:
    def draw(p):
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(6, 3),
                    QPointF(16, 3),
                    QPointF(16, 19),
                    QPointF(11, 15),
                    QPointF(6, 19),
                ]
            )
        )

    return _build(draw)


def build_form_fields_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(5, 3, 12, 16), 1.5, 1.5)
        p.drawRect(QRectF(7.5, 7, 2.5, 2.5))
        p.drawLine(QPointF(11.5, 8.2), QPointF(15, 8.2))
        p.drawRect(QRectF(7.5, 12, 2.5, 2.5))
        p.drawLine(QPointF(11.5, 13.2), QPointF(15, 13.2))

    return _build(draw)


def build_annotations_icon() -> QIcon:
    def draw(p):
        p.save()
        p.translate(11, 10)
        p.rotate(45)
        p.drawRoundedRect(QRectF(-3, -9, 6, 14), 1.5, 1.5)
        p.drawLine(QPointF(-3, 3), QPointF(3, 3))
        p.restore()
        p.drawLine(QPointF(4, 19), QPointF(16, 19))

    return _build(draw)
