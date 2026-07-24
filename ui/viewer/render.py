"""Conversão de páginas pypdfium2 para QPixmap."""

from PIL.ImageQt import ImageQt
from PySide6.QtGui import QImage, QPixmap


def render_page(pdfium_page, scale: float) -> QPixmap:
    """Renderiza uma página do pypdfium2 em um QPixmap na escala pedida."""
    bitmap = pdfium_page.render(scale=scale, draw_annots=True)
    pil_image = bitmap.to_pil()
    qimage = ImageQt(pil_image)
    return QPixmap.fromImage(QImage(qimage))
