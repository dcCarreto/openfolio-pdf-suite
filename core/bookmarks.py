"""Marcadores (sumário/outline) de navegação em arquivos PDF."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class AddBookmarks(PDFOperation):
    """Adiciona marcadores de navegação (outline) a um PDF."""

    def run(self, input_path: str, output_path: str, bookmarks: list[tuple[str, int]]) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        for title, page_number in bookmarks:
            writer.add_outline_item(title, page_number)

        with open(output_path, "wb") as f:
            writer.write(f)
