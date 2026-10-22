"""Mesclagem de múltiplos arquivos PDF em um único documento."""

from .base import open_reader, write_pdf
from .document import pages_writer
from .progress import Progress, ensure_progress


class MergePDF:
    """Mescla uma lista de arquivos PDF em um único arquivo de saída.

    Marcadores, links e campos de formulário de cada arquivo vão junto; metadados, idioma
    e preferências de exibição vêm do primeiro; camadas e anexos de todos.
    """

    def run(self, input_paths: list[str], output_path: str, progress: Progress | None = None) -> None:
        progress = ensure_progress(progress)
        if not input_paths:
            raise ValueError("Informe ao menos um arquivo PDF para mesclar.")
        readers = [open_reader(path) for path in progress.steps(input_paths, message="Lendo os arquivos")]
        parts = [(reader, list(range(len(reader.pages)))) for reader in readers]
        writer = pages_writer(parts)
        progress.update(0, 0, "Gravando")
        write_pdf(writer, output_path)
