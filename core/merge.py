"""Mesclagem de múltiplos arquivos PDF em um único documento."""

from .base import PDFOperation


class MergePDF(PDFOperation):
    """Mescla uma lista de arquivos PDF em um único arquivo de saída."""

    def run(self, input_paths: list[str], output_path: str) -> None:
        raise NotImplementedError
