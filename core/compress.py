"""Compressão de arquivos PDF."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, write_pdf
from .progress import Progress, ensure_progress


class CompressPDF(PDFOperation):
    """Reduz o tamanho de um arquivo PDF recomprimindo conteúdo e removendo objetos
    duplicados ou sem uso. Trabalha sobre uma cópia completa do documento: marcadores,
    formulário, anexos e metadados continuam lá. Ainda não recomprime imagens."""

    def run(self, input_path: str, output_path: str, progress: Progress | None = None) -> None:
        progress = ensure_progress(progress)
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        for page in progress.steps(writer.pages, len(writer.pages), "Comprimindo páginas"):
            page.compress_content_streams()

        progress.update(0, 0, "Removendo objetos repetidos")
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        progress.check()
        write_pdf(writer, output_path)
