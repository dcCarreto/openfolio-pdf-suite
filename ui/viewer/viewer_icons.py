"""Ícones das barras, do visualizador e dos estados, desenhados em runtime na mesma grade de
24 × 24 de ui/sidebar_icons.py (ver `ui/icon_utils.py`)."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QPainterPath, QPen, QPolygonF

from ui.icon_utils import build_icon as _build
from ui.icon_utils import filled, hollow

R = 2.5  # raio dos cantos


def _poly(p, *points, closed=False):
    polygon = QPolygonF([QPointF(x, y) for x, y in points])
    p.drawPolygon(polygon) if closed else p.drawPolyline(polygon)


def _magnifier(p):
    p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    p.drawLine(QPointF(15.5, 15.5), QPointF(20, 20))


def _arc_arrow(p, clockwise: bool):
    """arrow-clockwise / -counter-clockwise: arco de 270° de raio 7 com a ponta em L."""
    rect = QRectF(5, 5, 14, 14)
    if clockwise:  # aberto em cima à direita; a ponta, no alto, aponta para a direita
        p.drawArc(rect, 90 * 16, 270 * 16)
        _poly(p, (9.5, 2.5), (12, 5), (9.5, 7.5))
    else:  # espelhado
        p.drawArc(rect, 90 * 16, -270 * 16)
        _poly(p, (14.5, 2.5), (12, 5), (14.5, 7.5))


# -- barra do visualizador ----------------------------------------------------------------


def build_open_icon() -> QIcon:
    """folder-open."""

    def draw(p):
        _poly(p, (3, 19), (3, 5), (9, 5), (11, 7.5), (18, 7.5), (18, 10))
        _poly(p, (3, 19), (6, 10), (21, 10), (18, 19), closed=True)

    return _build(draw)


def build_prev_page_icon() -> QIcon:
    """caret-left."""

    def draw(p):
        _poly(p, (15, 6), (9, 12), (15, 18))

    return _build(draw)


def build_next_page_icon() -> QIcon:
    """caret-right."""

    def draw(p):
        _poly(p, (9, 6), (15, 12), (9, 18))

    return _build(draw)


def build_zoom_in_icon() -> QIcon:
    def draw(p):
        _magnifier(p)
        p.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))
        p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))

    return _build(draw)


def build_zoom_out_icon() -> QIcon:
    def draw(p):
        _magnifier(p)
        p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))

    return _build(draw)


def build_fit_width_icon() -> QIcon:
    """arrows-out-line-horizontal."""

    def draw(p):
        p.drawLine(QPointF(3, 4), QPointF(3, 20))
        p.drawLine(QPointF(21, 4), QPointF(21, 20))
        p.drawLine(QPointF(7, 12), QPointF(17, 12))
        _poly(p, (10, 9), (7, 12), (10, 15))
        _poly(p, (14, 9), (17, 12), (14, 15))

    return _build(draw)


def build_fit_page_icon() -> QIcon:
    """arrows-out-line-vertical."""

    def draw(p):
        p.drawLine(QPointF(4, 3), QPointF(20, 3))
        p.drawLine(QPointF(4, 21), QPointF(20, 21))
        p.drawLine(QPointF(12, 7), QPointF(12, 17))
        _poly(p, (9, 10), (12, 7), (15, 10))
        _poly(p, (9, 14), (12, 17), (15, 14))

    return _build(draw)


def build_single_page_icon() -> QIcon:
    """file: uma página."""

    def draw(p):
        p.drawRoundedRect(QRectF(6, 3, 12, 18), R, R)

    return _build(draw)


def build_continuous_page_icon() -> QIcon:
    """rows: dois retângulos empilhados."""

    def draw(p):
        p.drawRoundedRect(QRectF(6, 3, 12, 8), 2, 2)
        p.drawRoundedRect(QRectF(6, 13, 12, 8), 2, 2)

    return _build(draw)


def build_double_page_icon() -> QIcon:
    """columns: dois retângulos lado a lado."""

    def draw(p):
        p.drawRoundedRect(QRectF(3, 5, 8, 14), 2, 2)
        p.drawRoundedRect(QRectF(13, 5, 8, 14), 2, 2)

    return _build(draw)


def build_book_icon() -> QIcon:
    """book-open."""

    def draw(p):
        path = QPainterPath(QPointF(12, 7))
        path.cubicTo(10, 5, 6, 4.5, 3, 5)
        path.lineTo(3, 18)
        path.cubicTo(6, 17.5, 10, 18, 12, 20)
        path.cubicTo(14, 18, 18, 17.5, 21, 18)
        path.lineTo(21, 5)
        path.cubicTo(18, 4.5, 14, 5, 12, 7)
        path.lineTo(12, 20)
        p.drawPath(path)

    return _build(draw)


def build_thumbnails_icon() -> QIcon:
    """images: as miniaturas, duas fotos sobrepostas."""

    def draw(p):
        p.drawRoundedRect(QRectF(7, 3, 14, 12), 2, 2)
        _poly(p, (17, 18), (17, 19), (3, 19), (3, 8), (4, 8))
        p.drawEllipse(QPointF(11.5, 7.5), 1.3, 1.3)
        _poly(p, (8, 14), (12.5, 10), (15.5, 12.5), (21, 8.5))

    return _build(draw)


def build_search_icon() -> QIcon:
    """magnifying-glass."""

    def draw(p):
        _magnifier(p)

    return _build(draw)


def build_rotate_icon() -> QIcon:
    """arrow-clockwise."""

    def draw(p):
        _arc_arrow(p, clockwise=True)

    return _build(draw)


def build_rotate_left_icon() -> QIcon:
    """arrow-counter-clockwise."""

    def draw(p):
        _arc_arrow(p, clockwise=False)

    return _build(draw)


def build_save_icon() -> QIcon:
    """floppy-disk."""

    def draw(p):
        _poly(p, (4, 4), (17, 4), (20, 7), (20, 20), (4, 20), closed=True)
        p.drawRoundedRect(QRectF(7.5, 13, 9, 7), 1, 1)
        p.drawLine(QPointF(8, 4), QPointF(8, 8.5))
        p.drawLine(QPointF(8, 8.5), QPointF(14.5, 8.5))
        p.drawLine(QPointF(14.5, 8.5), QPointF(14.5, 4))

    return _build(draw)


def build_print_icon() -> QIcon:
    """printer."""

    def draw(p):
        _poly(p, (7, 8), (7, 3), (17, 3), (17, 8))
        _poly(p, (7, 17), (3.5, 17), (3.5, 8), (20.5, 8), (20.5, 17), (17, 17))
        p.drawRect(QRectF(7, 14, 10, 7))
        filled(p)
        p.drawEllipse(QPointF(17, 11.2), 0.9, 0.9)
        hollow(p)

    return _build(draw)


def build_close_icon() -> QIcon:
    """x."""

    def draw(p):
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))

    return _build(draw)


def build_plus_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))

    return _build(draw)


def build_minus_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(5, 12), QPointF(19, 12))

    return _build(draw)


def build_caret_down_icon() -> QIcon:
    """caret-down: o "▾" dos botões com mais opções (Realce, Formas, Estilo)."""

    def draw(p):
        _poly(p, (7.5, 10), (12, 14.5), (16.5, 10))

    return _build(draw)


def build_caret_right_icon() -> QIcon:
    """caret-right: uma seção recolhida (Opções avançadas)."""

    def draw(p):
        _poly(p, (10, 7.5), (14.5, 12), (10, 16.5))

    return _build(draw)


def build_check_icon() -> QIcon:
    def draw(p):
        _poly(p, (5, 12.5), (10, 17.5), (19, 7.5))

    return _build(draw)


def build_more_icon() -> QIcon:
    """dots-three."""

    def draw(p):
        filled(p)
        for x in (6, 12, 18):
            p.drawEllipse(QPointF(x, 12), 1.4, 1.4)
        hollow(p)

    return _build(draw)


def build_home_icon() -> QIcon:
    """house."""

    def draw(p):
        _poly(p, (4, 11), (12, 4), (20, 11))
        _poly(p, (6, 9.5), (6, 20), (18, 20), (18, 9.5))
        _poly(p, (10, 20), (10, 15), (14, 15), (14, 20))

    return _build(draw)


def build_file_icon() -> QIcon:
    """file-pdf: a página com a dobra e três linhas."""

    def draw(p):
        _poly(p, (5, 3), (14, 3), (19, 8), (19, 21), (5, 21), closed=True)
        _poly(p, (14, 3), (14, 8), (19, 8))
        p.drawLine(QPointF(8, 13), QPointF(16, 13))
        p.drawLine(QPointF(8, 16), QPointF(16, 16))
        p.drawLine(QPointF(8, 18.5), QPointF(13, 18.5))

    return _build(draw)


def build_file_drop_icon() -> QIcon:
    """file-arrow-up: o estado sem documento e a área de soltar."""

    def draw(p):
        _poly(p, (5, 3), (14, 3), (19, 8), (19, 21), (5, 21), closed=True)
        _poly(p, (14, 3), (14, 8), (19, 8))
        p.drawLine(QPointF(12, 18), QPointF(12, 11))
        _poly(p, (9, 14), (12, 11), (15, 14))

    return _build(draw)


def build_file_dashed_icon() -> QIcon:
    """file-dashed: a entrada ainda sem arquivo."""

    def draw(p):
        pen = QPen(p.pen())
        pen.setDashPattern([2, 2])
        p.setPen(pen)
        _poly(p, (5, 3), (14, 3), (19, 8), (19, 21), (5, 21), closed=True)

    return _build(draw)


def build_pin_icon() -> QIcon:
    """push-pin: a ferramenta está no trilho rápido."""

    def draw(p):
        _poly(p, (9, 3), (15, 3))
        _poly(p, (10, 3), (10, 9), (6.5, 13), (17.5, 13), (14, 9), (14, 3))
        p.drawLine(QPointF(12, 13), QPointF(12, 21))

    return _build(draw)


def build_duplicate_icon() -> QIcon:
    """copy."""

    def draw(p):
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 2, 2)
        _poly(p, (16, 8), (16, 4), (4, 4), (4, 16), (8, 16))

    return _build(draw)


def build_trash_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(4, 6), QPointF(20, 6))
        _poly(p, (9, 6), (9, 3.5), (15, 3.5), (15, 6))
        _poly(p, (6, 6), (7, 20), (17, 20), (18, 6))
        p.drawLine(QPointF(10, 10), QPointF(10, 16.5))
        p.drawLine(QPointF(14, 10), QPointF(14, 16.5))

    return _build(draw)


# -- estados e tarefas ----------------------------------------------------------------------


def build_check_circle_icon(color=None) -> QIcon:
    """check-circle preenchido (sucesso)."""

    def draw(p):
        filled(p)
        p.drawEllipse(QPointF(12, 12), 9, 9)
        p.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        hollow(p)
        _poly(p, (8, 12.5), (11, 15.5), (16.5, 9.5))

    return _build(draw, color=color)


def build_warning_circle_icon(color=None) -> QIcon:
    """warning-circle preenchido (erro)."""

    def draw(p):
        filled(p)
        p.drawEllipse(QPointF(12, 12), 9, 9)
        p.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(12, 7.5), QPointF(12, 13))
        p.drawPoint(QPointF(12, 16.5))

    return _build(draw, color=color)


def build_clock_icon() -> QIcon:
    def draw(p):
        p.drawEllipse(QPointF(12, 12), 9, 9)
        _poly(p, (12, 7), (12, 12), (15.5, 14))

    return _build(draw)


def build_list_checks_icon(color=None) -> QIcon:
    """list-checks: as tarefas (no acento, `color="accent"`, na barra de status)."""

    def draw(p):
        _poly(p, (3.5, 6.5), (5, 8), (8, 5))
        _poly(p, (3.5, 13.5), (5, 15), (8, 12))
        p.drawLine(QPointF(11, 6.5), QPointF(20, 6.5))
        p.drawLine(QPointF(11, 13.5), QPointF(20, 13.5))
        p.drawLine(QPointF(11, 19), QPointF(20, 19))

    return _build(draw, color=color)


def build_update_icon() -> QIcon:
    """arrow-circle-down: atualização disponível."""

    def draw(p):
        p.drawEllipse(QPointF(12, 12), 9, 9)
        p.drawLine(QPointF(12, 7.5), QPointF(12, 16))
        _poly(p, (8.5, 12.5), (12, 16), (15.5, 12.5))

    return _build(draw)


# -- barra de marcação (ui/viewer/markup_bar.py) ---------------------------------------------


def _draw_select(p):
    """cursor."""
    _poly(p, (6, 4), (6, 18), (10, 14), (13, 20), (15, 19), (12, 13), (18, 13), closed=True)


def _draw_highlight(p):
    """highlighter, como o de Anotações."""
    _poly(p, (9, 15), (17, 7), (20.5, 10.5), (12.5, 18.5), closed=True)
    _poly(p, (9, 15), (6, 18), (9.5, 18.5), (12.5, 18.5))
    p.drawLine(QPointF(4, 21), QPointF(12, 21))


def _draw_underline(p):
    """text-underline."""
    path = QPainterPath(QPointF(8, 4))
    path.lineTo(8, 11)
    path.arcTo(QRectF(8, 7, 8, 8), 180, 180)
    path.lineTo(16, 4)
    p.drawPath(path)
    p.drawLine(QPointF(6, 20), QPointF(18, 20))


def _draw_strikeout(p):
    """text-strikethrough: um "S" e a linha no meio."""
    path = QPainterPath(QPointF(16.5, 6.5))
    path.cubicTo(15, 4, 8, 3.5, 7.5, 7.5)
    path.cubicTo(7, 11, 17, 12, 16.5, 16.5)
    path.cubicTo(16, 20.5, 8.5, 20.5, 7, 17.5)
    p.drawPath(path)
    p.drawLine(QPointF(4, 12), QPointF(20, 12))


def _draw_note(p):
    """note-blank: o quadrado com o canto dobrado."""
    _poly(p, (4, 4), (20, 4), (20, 14), (14, 20), (4, 20), closed=True)
    _poly(p, (20, 14), (14, 14), (14, 20))


def _draw_ink(p):
    """pen: a caneta a 45° e um traço de mão livre."""
    _poly(p, (5, 19), (6, 15), (16, 5), (19, 8), (9, 18), closed=True)
    p.drawLine(QPointF(14, 7), QPointF(17, 10))
    path = QPainterPath(QPointF(12, 21))
    path.cubicTo(14, 19.5, 16, 22, 20, 20)
    p.drawPath(path)


def _draw_square(p):
    p.drawRoundedRect(QRectF(4, 5, 16, 14), R, R)


def _draw_circle(p):
    p.drawEllipse(QPointF(12, 12), 8, 8)


def _draw_arrow(p):
    """arrow-up-right."""
    p.drawLine(QPointF(6, 18), QPointF(18, 6))
    _poly(p, (9, 6), (18, 6), (18, 15))


def _draw_stamp(p):
    p.drawRoundedRect(QRectF(10, 4, 4, 6), 2, 2)
    p.drawLine(QPointF(12, 10), QPointF(12, 13))
    p.drawRoundedRect(QRectF(5, 13, 14, 4), 1.5, 1.5)
    p.drawLine(QPointF(6, 20), QPointF(18, 20))


_MARKUP_DRAW = {
    "select": _draw_select,
    "highlight": _draw_highlight,
    "underline": _draw_underline,
    "strikeout": _draw_strikeout,
    "note": _draw_note,
    "ink": _draw_ink,
    "square": _draw_square,
    "circle": _draw_circle,
    "arrow": _draw_arrow,
    "stamp": _draw_stamp,
}


def build_markup_icon(tool: str) -> QIcon:
    """Ícone de uma ferramenta de marcação (`ui.annotation_state.TOOLS`)."""
    return _build(_MARKUP_DRAW[tool])
