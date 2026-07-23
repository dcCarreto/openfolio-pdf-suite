"""Conversão de arquivos XML para PDF: imprime o conteúdo formatado como texto."""

import xml.dom.minidom

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .base import PDFOperation


class ConvertXMLToPDF(PDFOperation):
    """Converte um arquivo XML para PDF, imprimindo o conteúdo indentado como texto."""

    def run(self, input_path: str, output_path: str, font_size: int = 8) -> None:
        with open(input_path, "r", encoding="utf-8") as f:
            raw = f.read()

        try:
            pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ")
            lines = [line for line in pretty.splitlines() if line.strip()]
        except Exception:
            lines = raw.splitlines() or [""]

        width, height = A4
        margin = 36
        line_height = font_size + 2

        c = canvas.Canvas(output_path, pagesize=A4)
        c.setFont("Courier", font_size)
        y = height - margin

        for line in lines:
            if y < margin:
                c.showPage()
                c.setFont("Courier", font_size)
                y = height - margin
            c.drawString(margin, y, line[:150])
            y -= line_height

        c.save()
