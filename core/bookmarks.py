"""Marcadores (sumário/outline) de navegação em arquivos PDF."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index, write_pdf


class AddBookmarks(PDFOperation):
    """Adiciona marcadores de navegação (outline) a um PDF, depois dos que ele já tem."""

    def run(self, input_path: str, output_path: str, bookmarks: list[tuple[str, int]]) -> None:
        reader = open_reader(input_path)
        for _title, page_number in bookmarks:
            require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=reader)
        for title, page_number in bookmarks:
            writer.add_outline_item(title, page_number)
        write_pdf(writer, output_path)
