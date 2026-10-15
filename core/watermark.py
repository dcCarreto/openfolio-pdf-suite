"""Marca d'água em arquivos PDF."""

from pypdf import PdfWriter
from reportlab.lib.colors import Color

from .base import PDFOperation, open_reader, write_pdf
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay


class AddWatermark(PDFOperation):
    """Adiciona uma marca d'água de texto sobre todas as páginas de um PDF, centralizada e
    girada em relação à página como ela aparece na tela (também em páginas com `/Rotate`)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        text: str,
        opacity: float = 0.3,
        font_size: int = 40,
        rotation: float = 45,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)

        def draw(canvas, width: float, height: float) -> None:
            canvas.translate(width / 2, height / 2)
            canvas.rotate(rotation)
            canvas.setFillColor(Color(0, 0, 0, alpha=opacity))
            canvas.setFont("Helvetica-Bold", font_size)
            canvas.drawCentredString(0, 0, text)

        for source_page, page in zip(reader.pages, writer.pages):
            page.merge_page(visual_overlay(PageGeometry.from_pypdf_page(source_page), draw))

        write_pdf(writer, output_path)
