"""Ícones da barra de ferramentas do visualizador, desenhados em runtime (mesma técnica
usada em ui/sidebar_icons.py)."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QIcon, QPolygonF

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


def build_double_page_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(2.5, 4, 8, 14), 1.2, 1.2)
        p.drawRoundedRect(QRectF(11.5, 4, 8, 14), 1.2, 1.2)

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


def build_fit_page_icon() -> QIcon:
    def draw(p):
        p.drawRoundedRect(QRectF(6, 3, 10, 16), 1.5, 1.5)
        p.drawLine(QPointF(11, 6), QPointF(11, 16))
        p.drawLine(QPointF(11, 6), QPointF(9, 8))
        p.drawLine(QPointF(11, 6), QPointF(13, 8))
        p.drawLine(QPointF(11, 16), QPointF(9, 14))
        p.drawLine(QPointF(11, 16), QPointF(13, 14))

    return _build(draw)


def build_rotate_icon() -> QIcon:
    def draw(p):
        p.drawArc(QRectF(4, 4, 14, 14), 90 * 16, 270 * 16)
        p.drawLine(QPointF(11, 4), QPointF(14, 2))
        p.drawLine(QPointF(11, 4), QPointF(14, 7))

    return _build(draw)


def build_save_icon() -> QIcon:
    """Salvar: um disquete."""

    def draw(p):
        p.drawPolygon(QPolygonF([QPointF(4, 4), QPointF(15, 4), QPointF(18, 7), QPointF(18, 18), QPointF(4, 18)]))
        p.drawRect(QRectF(7, 4, 7, 4))
        p.drawRect(QRectF(7, 12, 8, 6))

    return _build(draw)


def build_print_icon() -> QIcon:
    """Imprimir: a impressora com a folha saindo."""

    def draw(p):
        p.drawRect(QRectF(7, 3, 8, 5))
        p.drawRoundedRect(QRectF(3, 8, 16, 7), 2, 2)
        p.drawRect(QRectF(7, 13, 8, 6))

    return _build(draw)


def build_close_icon() -> QIcon:
    """Fechar a aba: um x fino."""

    def draw(p):
        p.drawLine(QPointF(7, 7), QPointF(15, 15))
        p.drawLine(QPointF(15, 7), QPointF(7, 15))

    return _build(draw)


def build_plus_icon() -> QIcon:
    """Abrir em aba nova: um "+"."""

    def draw(p):
        p.drawLine(QPointF(11, 5), QPointF(11, 17))
        p.drawLine(QPointF(5, 11), QPointF(17, 11))

    return _build(draw)


def build_home_icon() -> QIcon:
    """Início: a casa."""

    def draw(p):
        p.drawPolyline(QPolygonF([QPointF(4, 10), QPointF(11, 4), QPointF(18, 10)]))
        p.drawRoundedRect(QRectF(6, 9, 10, 9), 1.5, 1.5)
        p.drawPolyline(QPolygonF([QPointF(9.5, 18), QPointF(9.5, 14), QPointF(12.5, 14), QPointF(12.5, 18)]))

    return _build(draw)


def build_file_icon() -> QIcon:
    """A aba de um documento: a folha com a dobra e as linhas do texto."""

    def draw(p):
        p.drawPolygon(QPolygonF([QPointF(5, 3), QPointF(13, 3), QPointF(17, 7), QPointF(17, 19), QPointF(5, 19)]))
        p.drawPolyline(QPolygonF([QPointF(13, 3), QPointF(13, 7), QPointF(17, 7)]))
        p.drawLine(QPointF(8, 11.5), QPointF(14, 11.5))
        p.drawLine(QPointF(8, 14.5), QPointF(12, 14.5))

    return _build(draw)


def build_book_icon() -> QIcon:
    """Livro (capa sozinha): o livro aberto."""

    def draw(p):
        p.drawPolygon(QPolygonF([QPointF(3, 5), QPointF(9, 5), QPointF(11, 7), QPointF(11, 18), QPointF(9, 16), QPointF(3, 16)]))
        p.drawPolygon(QPolygonF([QPointF(19, 5), QPointF(13, 5), QPointF(11, 7), QPointF(11, 18), QPointF(13, 16), QPointF(19, 16)]))

    return _build(draw)


def build_more_icon() -> QIcon:
    """Mais opções: três pontos."""

    def draw(p):
        for x in (6, 11, 16):
            p.drawEllipse(QRectF(x - 1, 10, 2, 2))

    return _build(draw)


# -- barra de marcação (ui/viewer/markup_bar.py) ---------------------------------------


def _letter(p, text: str, underline: bool = False, strike: bool = False):
    font = QFont(p.font())
    font.setPixelSize(13)
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    p.drawText(QRectF(3, 2, 16, 15), 0x0084, text)  # AlignHCenter | AlignVCenter
    if underline:
        p.drawLine(QPointF(6, 18.5), QPointF(16, 18.5))
    if strike:
        p.drawLine(QPointF(4, 10), QPointF(18, 10))


def _draw_select(p):
    p.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(16, 13), QPointF(11.5, 13.5), QPointF(14, 19), QPointF(12, 20), QPointF(9.5, 14.5), QPointF(6, 17)]))


def _draw_highlight(p):
    p.drawPolygon(QPolygonF([QPointF(13, 3), QPointF(18, 8), QPointF(10, 16), QPointF(5, 11)]))
    p.drawLine(QPointF(5, 11), QPointF(3, 17))
    p.drawLine(QPointF(3, 17), QPointF(7, 17))
    p.drawLine(QPointF(10, 19.5), QPointF(19, 19.5))


def _draw_note(p):
    p.drawPolygon(QPolygonF([QPointF(4, 4), QPointF(18, 4), QPointF(18, 13), QPointF(13, 18), QPointF(4, 18)]))
    p.drawLine(QPointF(13, 18), QPointF(13, 13))
    p.drawLine(QPointF(13, 13), QPointF(18, 13))


def _draw_ink(p):
    p.drawLine(QPointF(5, 17), QPointF(15, 7))
    p.drawLine(QPointF(15, 7), QPointF(17, 9))
    p.drawLine(QPointF(17, 9), QPointF(7, 19))
    p.drawLine(QPointF(7, 19), QPointF(4, 20))
    p.drawLine(QPointF(4, 20), QPointF(5, 17))
    p.drawLine(QPointF(16, 6), QPointF(18, 4))


def _draw_square(p):
    p.drawRoundedRect(QRectF(4, 5, 14, 12), 1.5, 1.5)


def _draw_circle(p):
    p.drawEllipse(QRectF(4, 4, 14, 14))


def _draw_arrow(p):
    p.drawLine(QPointF(5, 17), QPointF(17, 5))
    p.drawLine(QPointF(17, 5), QPointF(10, 5))
    p.drawLine(QPointF(17, 5), QPointF(17, 12))


def _draw_stamp(p):
    p.drawRoundedRect(QRectF(8.5, 3, 5, 6), 2, 2)
    p.drawLine(QPointF(11, 9), QPointF(11, 12))
    p.drawRoundedRect(QRectF(4, 12, 14, 4), 1, 1)
    p.drawLine(QPointF(5, 19), QPointF(17, 19))


_MARKUP_DRAW = {
    "select": _draw_select,
    "highlight": _draw_highlight,
    "underline": lambda p: _letter(p, "U", underline=True),
    "strikeout": lambda p: _letter(p, "S", strike=True),
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


def build_check_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(5, 11.5), QPointF(9.5, 16))
        p.drawLine(QPointF(9.5, 16), QPointF(17, 7))

    return _build(draw)


def build_minus_icon() -> QIcon:
    def draw(p):
        p.drawLine(QPointF(6, 11), QPointF(16, 11))

    return _build(draw)
