"""Criação de novos arquivos PDF em branco."""

from pypdf import PdfWriter

from .base import PDFOperation


class CreateBlankPDF(PDFOperation):
    """Cria um novo PDF com uma ou mais páginas em branco."""

    def run(
        self, output_path: str, page_count: int = 1, width: float = 595, height: float = 842
    ) -> None:
        if page_count < 1:
            raise ValueError("page_count deve ser maior ou igual a 1.")
        writer = PdfWriter()
        for _ in range(page_count):
            writer.add_blank_page(width=width, height=height)

        with open(output_path, "wb") as f:
            writer.write(f)
