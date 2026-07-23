"""Compressão de arquivos PDF."""

from .base import PDFOperation


class CompressPDF(PDFOperation):
    """Reduz o tamanho de um arquivo PDF."""

    def run(self, input_path: str, output_path: str) -> None:
        raise NotImplementedError
