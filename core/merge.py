"""Mesclagem de múltiplos arquivos PDF em um único documento."""

from pathlib import Path

from .base import open_reader, write_pdf
from .document import pages_writer
from .progress import Progress, ensure_progress


class MergePDF:
    """Mescla uma lista de arquivos PDF em um único arquivo de saída.

    Marcadores, links e campos de formulário de cada arquivo vão junto; metadados, idioma
    e preferências de exibição vêm do primeiro; camadas e anexos de todos.

    - `pages`: as páginas de cada arquivo (índices a partir de 0, na ordem dada; None = todas).
    - `bookmark_per_file`: um marcador com o nome de cada arquivo, na primeira página dele, com
      os marcadores do arquivo dentro.
    - `interleave`: dois arquivos, página a página (frentes e versos escaneados à parte);
      `reverse_second` lê o segundo de trás para frente, como sai do scanner ao virar o maço.
      Se um tiver mais páginas, as que sobram vão no fim.
    """

    def run(
        self,
        input_paths: list[str],
        output_path: str,
        progress: Progress | None = None,
        *,
        pages: list[list[int] | None] | None = None,
        bookmark_per_file: bool = False,
        interleave: bool = False,
        reverse_second: bool = False,
    ) -> None:
        progress = ensure_progress(progress)
        if not input_paths:
            raise ValueError("Informe ao menos um arquivo PDF para mesclar.")
        if interleave and len(input_paths) != 2:
            raise ValueError("Para intercalar, informe exatamente dois arquivos: o das frentes e o dos versos.")
        if pages is not None and len(pages) != len(input_paths):
            raise ValueError("Informe as páginas de cada arquivo (ou nenhuma).")
        readers = [open_reader(path) for path in progress.steps(input_paths, message="Lendo os arquivos")]
        selections = []
        for path, reader, chosen in zip(input_paths, readers, pages or [None] * len(readers)):
            total = len(reader.pages)
            if chosen is not None and not all(0 <= index < total for index in chosen):
                raise ValueError(f"{Path(path).name} tem {total} página(s): confira as páginas escolhidas.")
            selections.append(list(range(total)) if chosen is None else list(chosen))
        if not any(selections):
            raise ValueError("Nenhuma página escolhida.")

        titles = [Path(path).stem for path in input_paths] if bookmark_per_file else [None] * len(input_paths)
        if interleave:
            parts, part_titles = _interleaved(readers, selections, titles, reverse_second)
        else:
            parts, part_titles = list(zip(readers, selections)), titles
        writer = pages_writer(parts, titles=part_titles)
        progress.update(0, 0, "Gravando")
        write_pdf(writer, output_path)


def _interleaved(readers, selections, titles, reverse_second):
    """Uma parte por página, alternando os dois arquivos; o título de cada arquivo vai na
    primeira parte dele."""
    first, second = selections[0], selections[1][::-1] if reverse_second else selections[1]
    parts, part_titles, titled = [], [], set()
    for position in range(max(len(first), len(second))):
        for source, chosen in ((0, first), (1, second)):
            if position < len(chosen):
                parts.append((readers[source], [chosen[position]]))
                part_titles.append(None if source in titled else titles[source])
                titled.add(source)
    return parts, part_titles
