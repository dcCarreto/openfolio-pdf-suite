"""Divisão de um arquivo PDF em múltiplos documentos."""

from .base import PDFOperation


class SplitPDF(PDFOperation):
    """Divide um PDF em partes conforme os critérios informados."""

    def run(self, input_path: str, output_dir: str) -> None:
        raise NotImplementedError
