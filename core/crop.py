"""Corte de margens e redimensionamento de páginas de um PDF."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class CropPages(PDFOperation):
    """Corta uma margem de cada lado das páginas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        left: float = 0,
        bottom: float = 0,
        right: float = 0,
        top: float = 0,
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            added_page = writer.add_page(page)
            box = added_page.mediabox
            added_page.mediabox.lower_left = (
                float(box.left) + left,
                float(box.bottom) + bottom,
            )
            added_page.mediabox.upper_right = (
                float(box.right) - right,
                float(box.top) - top,
            )

        with open(output_path, "wb") as f:
            writer.write(f)


class ScalePages(PDFOperation):
    """Redimensiona as páginas de um PDF para um novo tamanho."""

    def run(self, input_path: str, output_path: str, width: float, height: float) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            added_page = writer.add_page(page)
            added_page.scale_to(width, height)

        with open(output_path, "wb") as f:
            writer.write(f)
