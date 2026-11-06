"""Conversão de páginas pypdfium2 para QImage/QPixmap.

O bitmap do pdfium vai direto para um QImage (4 bytes por pixel, a mesma ordem que o Qt usa
na tela), sem passar pelo PIL: antes eram três cópias da imagem por página. Um QImage pode
ser criado fora da thread da interface (ver `ui/viewer/page_renderer.py`); um QPixmap, não.
"""

from PySide6.QtGui import QImage, QPixmap

from core.base import render_scale
from core.progress import PDFIUM_LOCK


def render_image(pdfium_page, scale: float, device_pixel_ratio: float = 1.0, rotation: int = 0) -> QImage:
    """Renderiza uma página do pypdfium2 num QImage na escala pedida.

    Em telas com escala (125%, 150%, 200%), renderiza com mais pixels e marca a imagem com
    o `device_pixel_ratio`: ela ocupa o mesmo espaço na tela, mas sem ficar borrada. Quem
    desenha por cima (anotações, redação, busca) continua usando coordenadas lógicas.
    """
    ratio = max(1.0, float(device_pixel_ratio))
    with PDFIUM_LOCK:
        # Página gigante: menos pixels, com o mesmo tamanho na tela (a razão diz quantos
        # pixels da imagem vão em cada pixel lógico, e as marcações continuam no lugar).
        total = render_scale(pdfium_page, scale * ratio)
        # `rotation`: giro só da tela, somado à /Rotate da página (sentido horário).
        # BGRx é o RGB32 do Qt (little-endian): a cópia abaixo é a única.
        bitmap = pdfium_page.render(scale=total, draw_annots=True, rotation=rotation, prefer_bgrx=True)
        try:
            image = QImage(bitmap.buffer, bitmap.width, bitmap.height, bitmap.stride, QImage.Format.Format_RGB32).copy()
        finally:
            bitmap.close()
    image.setDevicePixelRatio(total / scale)
    return image


def render_page(pdfium_page, scale: float, device_pixel_ratio: float = 1.0, rotation: int = 0) -> QPixmap:
    """Como `render_image`, já como QPixmap (só na thread da interface)."""
    return to_pixmap(render_image(pdfium_page, scale, device_pixel_ratio, rotation))


def to_pixmap(image: QImage) -> QPixmap:
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(image.devicePixelRatio())
    return pixmap


def logical_size(pixmap: QPixmap):
    """Tamanho do pixmap em pixels lógicos (o que ele ocupa na tela)."""
    return pixmap.deviceIndependentSize().toSize()
