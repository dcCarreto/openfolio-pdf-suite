"""Numeração de páginas em arquivos PDF."""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from .base import PDFOperation, open_reader


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
        reader = open_reader(input_path)
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


_BATES_POSITIONS = {
    "bottom-right": lambda w, h, margin: (w - margin, margin, "right"),
    "bottom-left": lambda w, h, margin: (margin, margin, "left"),
    "top-right": lambda w, h, margin: (w - margin, h - margin, "right"),
    "top-left": lambda w, h, margin: (margin, h - margin, "left"),
}


class AddBatesNumbers(PDFOperation):
    """Adiciona numeração Bates a um PDF: prefixo + sequência global com zeros à esquerda
    (ex.: "CASO-000001"), usada em processos jurídicos para referenciar páginas de forma
    única entre vários documentos — diferente da numeração de página comum, que reinicia
    por documento e não serve como identificador único entre arquivos.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        prefix: str = "",
        start_at: int = 1,
        digits: int = 6,
        font_size: int = 9,
        margin: float = 18,
        position: str = "bottom-right",
    ) -> None:
        if position not in _BATES_POSITIONS:
            raise ValueError(f"Posição inválida: {position}")
        if digits < 1:
            raise ValueError("digits deve ser pelo menos 1.")

        reader = open_reader(input_path)
        writer = PdfWriter()

        for index, page in enumerate(reader.pages):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            label = f"{prefix}{start_at + index:0{digits}d}"
            x, y, align = _BATES_POSITIONS[position](width, height, margin)

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=(width, height))
            c.setFont("Helvetica", font_size)
            if align == "right":
                c.drawRightString(x, y, label)
            else:
                c.drawString(x, y, label)
            c.save()
            buffer.seek(0)

            stamped_page = PdfReader(buffer).pages[0]
            added_page = writer.add_page(page)
            added_page.merge_page(stamped_page)

        with open(output_path, "wb") as f:
            writer.write(f)


_HF_POSITIONS = {
    "header-left": lambda w, h, margin: (margin, h - margin, "left"),
    "header-center": lambda w, h, margin: (w / 2, h - margin, "center"),
    "header-right": lambda w, h, margin: (w - margin, h - margin, "right"),
    "footer-left": lambda w, h, margin: (margin, margin, "left"),
    "footer-center": lambda w, h, margin: (w / 2, margin, "center"),
    "footer-right": lambda w, h, margin: (w - margin, margin, "right"),
}


class AddHeaderFooter(PDFOperation):
    """Adiciona um texto livre de cabeçalho ou rodapé a todas as páginas de um PDF.

    Suporta os placeholders `{page}` (número da página) e `{pages}` (total de páginas) no
    texto — ex.: `"Página {page} de {pages}"` — resolvidos por página com `str.format()`.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        text: str,
        position: str = "footer-center",
        font_size: int = 10,
        margin: float = 24,
    ) -> None:
        if position not in _HF_POSITIONS:
            raise ValueError(f"Posição inválida: {position}")

        reader = open_reader(input_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)

        for index, page in enumerate(reader.pages):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            try:
                rendered = text.format(page=index + 1, pages=total_pages)
            except (KeyError, IndexError) as exc:
                raise ValueError(f"Placeholder inválido no texto: {exc}") from exc
            x, y, align = _HF_POSITIONS[position](width, height, margin)

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=(width, height))
            c.setFont("Helvetica", font_size)
            if align == "left":
                c.drawString(x, y, rendered)
            elif align == "right":
                c.drawRightString(x, y, rendered)
            else:
                c.drawCentredString(x, y, rendered)
            c.save()
            buffer.seek(0)

            stamped_page = PdfReader(buffer).pages[0]
            added_page = writer.add_page(page)
            added_page.merge_page(stamped_page)

        with open(output_path, "wb") as f:
            writer.write(f)
