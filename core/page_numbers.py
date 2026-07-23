"""Numeração de páginas em arquivos PDF."""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from .base import PDFOperation


class AddPageNumbers(PDFOperation):
    """Adiciona números de página no rodapé de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        start_at: int = 1,
        font_size: int = 10,
        margin: float = 24,
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for index, page in enumerate(reader.pages):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            page_number = start_at + index

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=(width, height))
            c.setFont("Helvetica", font_size)
            c.drawCentredString(width / 2, margin, str(page_number))
            c.save()
            buffer.seek(0)

            numbered_page = PdfReader(buffer).pages[0]
            added_page = writer.add_page(page)
            added_page.merge_page(numbered_page)

        with open(output_path, "wb") as f:
            writer.write(f)
