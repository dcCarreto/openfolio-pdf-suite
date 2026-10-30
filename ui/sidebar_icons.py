"""Ícones das ferramentas, desenhados em runtime numa grade de 24 × 24 (traço linear de 1,5,
pontas arredondadas, cantos de raio 2,5; ver `ui/icon_utils.py`).

Emoji dependem de uma fonte de emoji instalada no sistema para renderizar
corretamente - suporte inconsistente entre plataformas (o bug das bandeiras
veio exatamente disso). Desenhar cada ícone como um glifo vetorial simples
garante o mesmo visual em qualquer sistema operacional.
"""

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QIcon, QPainterPath, QPolygonF

from ui.icon_utils import build_icon as _build
from ui.icon_utils import filled, hollow

R = 2.5  # raio dos cantos


def _poly(p, *points, closed=False):
    polygon = QPolygonF([QPointF(x, y) for x, y in points])
    p.drawPolygon(polygon) if closed else p.drawPolyline(polygon)


def _page(p, folded=True):
    """O contorno de uma página com a dobra no canto (file-pdf)."""
    _poly(p, (5, 3), (14, 3), (19, 8), (19, 21), (5, 21), closed=True)
    if folded:
        _poly(p, (14, 3), (14, 8), (19, 8))


def build_create_icon() -> QIcon:
    """file-plus: página com "+"."""

    def draw(p):
        _page(p)
        p.drawLine(QPointF(12, 11), QPointF(12, 18))
        p.drawLine(QPointF(8.5, 14.5), QPointF(15.5, 14.5))

    return _build(draw)


def build_merge_icon() -> QIcon:
    """arrows-merge: duas linhas que descem e se juntam numa seta."""

    def draw(p):
        path = QPainterPath(QPointF(7, 3))
        path.lineTo(7, 7)
        path.cubicTo(7, 10, 12, 10, 12, 13)
        path.moveTo(17, 3)
        path.lineTo(17, 7)
        path.cubicTo(17, 10, 12, 10, 12, 13)
        path.lineTo(12, 21)
        p.drawPath(path)
        _poly(p, (9, 18), (12, 21), (15, 18))

    return _build(draw)


def build_split_icon() -> QIcon:
    """Tesoura."""

    def draw(p):
        p.drawEllipse(QPointF(7, 17), 3, 3)
        p.drawEllipse(QPointF(17, 17), 3, 3)
        p.drawLine(QPointF(9, 15), QPointF(18, 4))
        p.drawLine(QPointF(15, 15), QPointF(6, 4))

    return _build(draw)


def build_pages_icon() -> QIcon:
    """arrow-clockwise sobre uma página: girar e reordenar páginas."""

    def draw(p):
        p.drawRoundedRect(QRectF(7, 6, 10, 13), 1.5, 1.5)
        p.drawArc(QRectF(3, 3, 18, 18), 110 * 16, 120 * 16)
        _poly(p, (3.5, 15.5), (4.2, 19), (7.4, 17.6))

    return _build(draw)


def build_organize_icon() -> QIcon:
    """squares-four."""

    def draw(p):
        for x, y in ((4, 4), (13.5, 4), (4, 13.5), (13.5, 13.5)):
            p.drawRoundedRect(QRectF(x, y, 6.5, 6.5), 1.5, 1.5)

    return _build(draw)


def build_fill_sign_icon() -> QIcon:
    """pen-nib: a ponta da caneta tinteiro."""

    def draw(p):
        _poly(p, (12, 3), (18, 12), (15, 20), (9, 20), (6, 12), closed=True)
        p.drawLine(QPointF(12, 3), QPointF(12, 12))
        p.drawEllipse(QPointF(12, 13.5), 1.5, 1.5)
        p.drawLine(QPointF(8, 20), QPointF(16, 20))

    return _build(draw)


def build_scan_cleanup_icon() -> QIcon:
    """Página torta e a página endireitada sobre ela."""

    def draw(p):
        _poly(p, (4, 7), (13, 4), (16, 15), (7, 18), closed=True)
        p.drawRoundedRect(QRectF(9, 8, 11, 13), 1.5, 1.5)

    return _build(draw)


def build_batch_icon() -> QIcon:
    """Três páginas empilhadas."""

    def draw(p):
        p.drawRoundedRect(QRectF(9, 3, 11, 13), 1.5, 1.5)
        _poly(p, (6.5, 6), (6.5, 18.5), (16, 18.5))
        _poly(p, (4, 9), (4, 21), (13, 21))

    return _build(draw)


def build_compress_icon() -> QIcon:
    """arrows-in-simple: duas setas diagonais apontando para o centro."""

    def draw(p):
        p.drawLine(QPointF(4, 4), QPointF(10, 10))
        _poly(p, (10, 5), (10, 10), (5, 10))
        p.drawLine(QPointF(20, 20), QPointF(14, 14))
        _poly(p, (14, 19), (14, 14), (19, 14))

    return _build(draw)


def build_convert_icon() -> QIcon:
    """arrows-left-right."""

    def draw(p):
        p.drawLine(QPointF(4, 8), QPointF(19, 8))
        _poly(p, (15.5, 4.5), (19, 8), (15.5, 11.5))
        p.drawLine(QPointF(20, 16), QPointF(5, 16))
        _poly(p, (8.5, 12.5), (5, 16), (8.5, 19.5))

    return _build(draw)


def build_watermark_icon() -> QIcon:
    """Gota."""

    def draw(p):
        path = QPainterPath(QPointF(12, 3))
        path.cubicTo(12, 3, 5, 10.5, 5, 14.5)
        path.cubicTo(5, 18.4, 8.1, 21, 12, 21)
        path.cubicTo(15.9, 21, 19, 18.4, 19, 14.5)
        path.cubicTo(19, 10.5, 12, 3, 12, 3)
        p.drawPath(path)

    return _build(draw)


def build_protect_icon(color=None) -> QIcon:
    """lock-simple (em `color`, um token, no cadeado da privacidade)."""

    def draw(p):
        p.drawRoundedRect(QRectF(5, 10, 14, 11), R, R)
        p.drawArc(QRectF(8, 3, 8, 10), 0, 180 * 16)
        p.drawLine(QPointF(8, 8), QPointF(8, 10))
        p.drawLine(QPointF(16, 8), QPointF(16, 10))

    return _build(draw, color=color)


def build_metadata_icon() -> QIcon:
    """info: círculo com "i"."""

    def draw(p):
        p.drawEllipse(QPointF(12, 12), 9, 9)
        p.drawLine(QPointF(12, 11), QPointF(12, 16.5))
        filled(p)
        p.drawEllipse(QPointF(12, 7.8), 1.1, 1.1)
        hollow(p)

    return _build(draw)


def build_page_numbers_icon() -> QIcon:
    """hash: #."""

    def draw(p):
        p.drawLine(QPointF(9.5, 4), QPointF(7.5, 20))
        p.drawLine(QPointF(16.5, 4), QPointF(14.5, 20))
        p.drawLine(QPointF(5, 9), QPointF(19.5, 9))
        p.drawLine(QPointF(4.5, 15), QPointF(19, 15))

    return _build(draw)


def build_extract_text_icon() -> QIcon:
    """Página com linhas de texto e uma seta saindo."""

    def draw(p):
        _poly(p, (12, 21), (5, 21), (5, 3), (14, 3), (19, 8), (19, 12))
        _poly(p, (14, 3), (14, 8), (19, 8))
        for y, right in ((11, 15), (14, 13), (17, 10)):
            p.drawLine(QPointF(8, y), QPointF(right, y))
        p.drawLine(QPointF(15, 16), QPointF(20, 20))
        _poly(p, (16.5, 20), (20, 20), (20, 16.5))

    return _build(draw)


def build_extract_images_icon() -> QIcon:
    """images: a foto com montanha e sol."""

    def draw(p):
        p.drawRoundedRect(QRectF(3, 5, 18, 14), R, R)
        p.drawEllipse(QPointF(9, 10), 1.6, 1.6)
        _poly(p, (4, 18), (10, 12.5), (14, 16), (16.5, 13.5), (20, 17))

    return _build(draw)


def build_crop_icon() -> QIcon:
    def draw(p):
        _poly(p, (7, 3), (7, 17), (21, 17))
        _poly(p, (3, 7), (17, 7), (17, 21))

    return _build(draw)


def build_bookmarks_icon() -> QIcon:
    """bookmark-simple."""

    def draw(p):
        _poly(p, (6, 4), (18, 4), (18, 20), (12, 16), (6, 20), closed=True)

    return _build(draw)


def build_form_fields_icon() -> QIcon:
    """textbox: um campo com o cursor de texto."""

    def draw(p):
        p.drawRoundedRect(QRectF(3, 6, 18, 12), R, R)
        p.drawLine(QPointF(8, 9), QPointF(8, 15))
        p.drawLine(QPointF(6.5, 9), QPointF(9.5, 9))
        p.drawLine(QPointF(6.5, 15), QPointF(9.5, 15))
        p.drawLine(QPointF(12, 12), QPointF(17, 12))

    return _build(draw)


def build_ocr_icon() -> QIcon:
    """scan: os quatro cantos do enquadramento e a linha de leitura."""

    def draw(p):
        _poly(p, (4, 8), (4, 4), (8, 4))
        _poly(p, (16, 4), (20, 4), (20, 8))
        _poly(p, (20, 16), (20, 20), (16, 20))
        _poly(p, (8, 20), (4, 20), (4, 16))
        p.drawLine(QPointF(6, 12), QPointF(18, 12))

    return _build(draw)


def build_redaction_icon() -> QIcon:
    """eye-slash: o olho riscado."""

    def draw(p):
        path = QPainterPath(QPointF(3, 12))
        path.cubicTo(6, 6.5, 18, 6.5, 21, 12)
        path.cubicTo(18, 17.5, 6, 17.5, 3, 12)
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 12), 3, 3)
        p.drawLine(QPointF(4, 4), QPointF(20, 20))

    return _build(draw)


def build_signature_icon() -> QIcon:
    """seal-check: o selo ondulado com o check."""

    def draw(p):
        points = []
        for step in range(16):
            angle = math.pi * 2 * step / 16 - math.pi / 2
            radius = 9 if step % 2 == 0 else 7.5
            points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
        _poly(p, *points, closed=True)
        _poly(p, (9, 12), (11, 14), (15, 10))

    return _build(draw)


def build_edit_icon() -> QIcon:
    """pencil-simple."""

    def draw(p):
        _poly(p, (4, 20), (4.5, 16), (16, 4.5), (19.5, 8), (8, 19.5), closed=True)
        p.drawLine(QPointF(13.5, 7), QPointF(17, 10.5))

    return _build(draw)


def build_layers_icon() -> QIcon:
    def draw(p):
        _poly(p, (12, 4), (21, 9), (12, 14), (3, 9), closed=True)
        _poly(p, (3, 13.5), (12, 18.5), (21, 13.5))

    return _build(draw)


def build_attachments_icon() -> QIcon:
    """paperclip."""

    def draw(p):
        path = QPainterPath(QPointF(16, 7))
        path.lineTo(8.5, 14.5)
        path.cubicTo(7, 16, 9, 18, 10.5, 16.5)
        path.lineTo(18, 9)
        path.cubicTo(21, 6, 17, 2, 14, 5)
        path.lineTo(6, 13)
        path.cubicTo(2, 17, 7.5, 22.5, 11.5, 18.5)
        path.lineTo(18, 12)
        p.drawPath(path)

    return _build(draw)


def build_measure_icon() -> QIcon:
    """Régua inclinada com as marcas."""

    def draw(p):
        _poly(p, (3, 17), (17, 3), (21, 7), (7, 21), closed=True)
        for step in (1, 2, 3, 4):
            x = 3 + step * 3.4
            y = 17 - step * 3.4
            length = 2.6 if step % 2 == 0 else 1.6
            p.drawLine(QPointF(x, y), QPointF(x + length, y + length))

    return _build(draw)


def build_accessibility_icon() -> QIcon:
    """O boneco de braços abertos."""

    def draw(p):
        p.drawEllipse(QPointF(12, 12), 9, 9)
        filled(p)
        p.drawEllipse(QPointF(12, 7.5), 1.3, 1.3)
        hollow(p)
        p.drawLine(QPointF(7.5, 10), QPointF(16.5, 10))
        _poly(p, (9.5, 17.5), (12, 13), (14.5, 17.5))
        p.drawLine(QPointF(12, 10), QPointF(12, 13))

    return _build(draw)


def build_compare_icon() -> QIcon:
    """columns: duas páginas lado a lado."""

    def draw(p):
        p.drawRoundedRect(QRectF(3, 4, 7.5, 16), 1.5, 1.5)
        p.drawRoundedRect(QRectF(13.5, 4, 7.5, 16), 1.5, 1.5)
        p.drawLine(QPointF(5.5, 9), QPointF(8, 9))
        p.drawLine(QPointF(16, 9), QPointF(18.5, 9))
        p.drawLine(QPointF(16, 13), QPointF(18.5, 13))

    return _build(draw)


def build_pdfa_icon() -> QIcon:
    """archive: a caixa de arquivo."""

    def draw(p):
        p.drawRoundedRect(QRectF(3, 4, 18, 5), 1.5, 1.5)
        _poly(p, (5, 9), (5, 20), (19, 20), (19, 9))
        p.drawLine(QPointF(10, 13), QPointF(14, 13))

    return _build(draw)


def build_annotations_icon() -> QIcon:
    """highlighter: o marcador inclinado sobre a linha de base."""

    def draw(p):
        _poly(p, (9, 15), (17, 7), (20.5, 10.5), (12.5, 18.5), closed=True)
        _poly(p, (9, 15), (6, 18), (9.5, 18.5), (12.5, 18.5))
        p.drawLine(QPointF(4, 21), QPointF(12, 21))

    return _build(draw)


def build_all_tools_icon() -> QIcon:
    """dots-nine."""

    def draw(p):
        filled(p)
        for x in (6, 12, 18):
            for y in (6, 12, 18):
                p.drawEllipse(QPointF(x, y), 1.4, 1.4)
        hollow(p)

    return _build(draw)
