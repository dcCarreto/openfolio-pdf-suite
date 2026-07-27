"""Mesclagem de múltiplos arquivos PDF em um único documento."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader


class MergePDF(PDFOperation):
    """Mescla uma lista de arquivos PDF em um único arquivo de saída."""

    def run(self, input_paths: list[str], output_path: str) -> None:
        if not input_paths:
            raise ValueError("Informe ao menos um arquivo PDF para mesclar.")
        writer = PdfWriter()
        for path in input_paths:
            open_reader(path)  # recusa PDFs protegidos por senha antes de anexar
            writer.append(path)
        with open(output_path, "wb") as f:
            writer.write(f)
