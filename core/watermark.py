"""Marca d'água em arquivos PDF."""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

from .base import PDFOperation


class AddWatermark(PDFOperation):
    """Adiciona uma marca d'água de texto sobre todas as páginas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        text: str,
        opacity: float = 0.3,
        font_size: int = 40,
        rotation: float = 45,
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=(width, height))
            c.saveState()
            c.translate(width / 2, height / 2)
            c.rotate(rotation)
            c.setFillColor(Color(0, 0, 0, alpha=opacity))
            c.setFont("Helvetica-Bold", font_size)
            c.drawCentredString(0, 0, text)
            c.restoreState()
            c.save()
            buffer.seek(0)

            watermark_page = PdfReader(buffer).pages[0]
            added_page = writer.add_page(page)
            added_page.merge_page(watermark_page)

        with open(output_path, "wb") as f:
            writer.write(f)
