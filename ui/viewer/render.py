"""Conversão de páginas pypdfium2 para QPixmap."""

from PIL.ImageQt import ImageQt
from PySide6.QtGui import QImage, QPixmap

from core.progress import PDFIUM_LOCK


def render_page(pdfium_page, scale: float, device_pixel_ratio: float = 1.0, rotation: int = 0) -> QPixmap:
    """Renderiza uma página do pypdfium2 em um QPixmap na escala pedida.

    Em telas com escala (125%, 150%, 200%), renderiza com mais pixels e marca o pixmap com
    o `device_pixel_ratio`: ele ocupa o mesmo espaço na tela, mas sem ficar borrado. Quem
    desenha por cima (anotações, redação, busca) continua usando coordenadas lógicas.
    """
    ratio = max(1.0, float(device_pixel_ratio))
    with PDFIUM_LOCK:
        # `rotation`: giro só da tela, somado à /Rotate da página (sentido horário).
        bitmap = pdfium_page.render(scale=scale * ratio, draw_annots=True, rotation=rotation)
        pil_image = bitmap.to_pil()
    pixmap = QPixmap.fromImage(QImage(ImageQt(pil_image)))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def logical_size(pixmap: QPixmap):
    """Tamanho do pixmap em pixels lógicos (o que ele ocupa na tela)."""
    return pixmap.deviceIndependentSize().toSize()
