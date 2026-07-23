"""Conversão de PDF para outros formatos e vice-versa."""

from .base import PDFOperation


class ConvertToImages(PDFOperation):
    """Converte páginas de um PDF em imagens."""

    def run(self, input_path: str, output_dir: str) -> None:
        raise NotImplementedError


class ConvertFromImages(PDFOperation):
    """Converte um conjunto de imagens em um PDF."""

    def run(self, input_paths: list[str], output_path: str) -> None:
        raise NotImplementedError
