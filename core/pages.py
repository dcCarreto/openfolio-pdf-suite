"""Manipulação de páginas: rotação, reordenação e remoção."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class RotatePages(PDFOperation):
    """Rotaciona páginas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        angle: int = 90,
        pages: list[int] | None = None,
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        target_pages = set(pages) if pages is not None else None
        for index, page in enumerate(reader.pages):
            if target_pages is None or index in target_pages:
                page.rotate(angle)
            writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)


class ReorderPages(PDFOperation):
    """Reordena páginas de um PDF."""

    def run(self, input_path: str, output_path: str, order: list[int]) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for index in order:
            writer.add_page(reader.pages[index])
        with open(output_path, "wb") as f:
            writer.write(f)


class RemovePages(PDFOperation):
    """Remove páginas de um PDF."""

    def run(self, input_path: str, output_path: str, pages: list[int]) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        pages_to_remove = set(pages)
        for index, page in enumerate(reader.pages):
            if index not in pages_to_remove:
                writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
