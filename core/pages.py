"""Manipulação de páginas: rotação, reordenação e remoção."""

from .base import PDFOperation


class RotatePages(PDFOperation):
    """Rotaciona páginas de um PDF."""

    def run(self, input_path: str, output_path: str) -> None:
        raise NotImplementedError


class ReorderPages(PDFOperation):
    """Reordena páginas de um PDF."""

    def run(self, input_path: str, output_path: str) -> None:
        raise NotImplementedError


class RemovePages(PDFOperation):
    """Remove páginas de um PDF."""

    def run(self, input_path: str, output_path: str) -> None:
        raise NotImplementedError
