"""Compressão de arquivos PDF."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, write_pdf


class CompressPDF(PDFOperation):
    """Reduz o tamanho de um arquivo PDF recomprimindo conteúdo e removendo objetos
    duplicados ou sem uso. Trabalha sobre uma cópia completa do documento: marcadores,
    formulário, anexos e metadados continuam lá. Ainda não recomprime imagens."""

    def run(self, input_path: str, output_path: str) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            page.compress_content_streams()

        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        write_pdf(writer, output_path)
