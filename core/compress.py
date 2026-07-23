"""Compressão de arquivos PDF."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class CompressPDF(PDFOperation):
    """Reduz o tamanho de um arquivo PDF recomprimindo conteúdo e removendo objetos duplicados."""

    def run(self, input_path: str, output_path: str) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            added_page = writer.add_page(page)
            added_page.compress_content_streams()

        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)

        with open(output_path, "wb") as f:
            writer.write(f)
