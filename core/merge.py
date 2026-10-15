"""Mesclagem de múltiplos arquivos PDF em um único documento."""

from .base import PDFOperation, open_reader, write_pdf
from .document import pages_writer


class MergePDF(PDFOperation):
    """Mescla uma lista de arquivos PDF em um único arquivo de saída.

    Marcadores, links e campos de formulário de cada arquivo vão junto; metadados, idioma
    e preferências de exibição vêm do primeiro; camadas e anexos de todos.
    """

    def run(self, input_paths: list[str], output_path: str) -> None:
        if not input_paths:
            raise ValueError("Informe ao menos um arquivo PDF para mesclar.")
        readers = [open_reader(path) for path in input_paths]
        parts = [(reader, list(range(len(reader.pages)))) for reader in readers]
        write_pdf(pages_writer(parts), output_path)
