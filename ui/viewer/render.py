"""Conversão de páginas pypdfium2 para QPixmap."""

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from core.base import render_scale
from core.progress import PDFIUM_LOCK


def render_page(pdfium_page, scale: float, device_pixel_ratio: float = 1.0, rotation: int = 0) -> QPixmap:
    """Renderiza uma página do pypdfium2 em um QPixmap na escala pedida.

    Em telas com escala (125%, 150%, 200%), renderiza com mais pixels e marca o pixmap com
    o `device_pixel_ratio`: ele ocupa o mesmo espaço na tela, mas sem ficar borrado. Quem
    desenha por cima (anotações, redação, busca) continua usando coordenadas lógicas.
    """
    ratio = max(1.0, float(device_pixel_ratio))
    with PDFIUM_LOCK:
        # Página gigante: menos pixels, com o mesmo tamanho na tela (a razão diz quantos
        # pixels da imagem vão em cada pixel lógico, e as marcações continuam no lugar).
        total = render_scale(pdfium_page, scale * ratio)
        # `rotation`: giro só da tela, somado à /Rotate da página (sentido horário).
        bitmap = pdfium_page.render(scale=total, draw_annots=True, rotation=rotation)
        pil_image = bitmap.to_pil()
    pixmap = QPixmap.fromImage(QImage(ImageQt(pil_image)))
    pixmap.setDevicePixelRatio(total / scale)
    return pixmap


def logical_size(pixmap: QPixmap):
    """Tamanho do pixmap em pixels lógicos (o que ele ocupa na tela)."""
    return pixmap.deviceIndependentSize().toSize()


def framed(pixmap: QPixmap) -> QPixmap:
    """Contorno cinza na miniatura: página branca sobre a lista branca do tema claro não aparece."""
    pixmap = QPixmap(pixmap)
    painter = QPainter(pixmap)
    painter.setPen(QColor("#9a9a9a"))
    painter.drawRect(QRectF(QPointF(), pixmap.deviceIndependentSize()).adjusted(0.5, 0.5, -0.5, -0.5))
    painter.end()
    return pixmap
