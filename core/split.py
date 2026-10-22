"""Divisão de um arquivo PDF em múltiplos documentos.

Cada parte leva os metadados, as camadas e os rótulos de página das suas páginas, e os
marcadores e links que apontam para elas (ver `core/document.py`). Os anexos do documento
original não são copiados para cada parte.
"""

import re
from pathlib import Path

from .base import open_reader, write_pdf
from .document import pages_writer


class SplitPDF:
    """Divide um PDF em partes de N páginas."""

    def run(
        self, input_path: str, output_dir: str, pages_per_file: int = 1
    ) -> list[str]:
        if pages_per_file < 1:
            raise ValueError("pages_per_file deve ser maior ou igual a 1.")
        reader = open_reader(input_path)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        total_pages = len(reader.pages)
        starts = list(range(0, total_pages, pages_per_file))
        digits = len(str(len(starts)))  # part01..part12: a ordem alfabética bate com a do documento
        output_paths = []
        for part_number, start in enumerate(starts, start=1):
            end = min(start + pages_per_file, total_pages)
            output_path = output_dir_path / f"{stem}_part{part_number:0{digits}d}.pdf"
            write_pdf(pages_writer([(reader, list(range(start, end)))], copy_attachments=False), str(output_path))
            output_paths.append(str(output_path))

        return output_paths


def _sanitize_filename(text: str) -> str:
    safe = re.sub(r"[^\w\-. ]", "_", text).strip()
    return safe[:60]


class SplitByBookmarks:
    """Divide um PDF em um arquivo por marcador de nível superior do sumário (outline):
    cada arquivo vai da página do marcador até a página anterior ao próximo marcador de
    nível superior (ou até o fim do documento, no último). Marcadores aninhados (subtópicos)
    não geram corte — só o nível superior do sumário divide o documento, pra não fatiar um
    PDF em dezenas de arquivos de uma única página quando o sumário é bem detalhado.

    As páginas antes do primeiro marcador (capa, sumário) viram uma parte própria,
    "00_inicio", em vez de sumirem.
    """

    def run(self, input_path: str, output_dir: str) -> list[str]:
        reader = open_reader(input_path)
        outline = reader.outline
        top_level = [item for item in outline if not isinstance(item, list)]
        if not top_level:
            raise ValueError("O PDF não tem marcadores de nível superior para dividir.")

        starts = []
        for item in top_level:
            try:
                page_number = reader.get_destination_page_number(item)
            except Exception:
                continue
            if page_number is not None:
                starts.append((item.title, page_number))
        starts.sort(key=lambda pair: pair[1])
        if not starts:
            raise ValueError("Não foi possível localizar a página de nenhum marcador.")

        total_pages = len(reader.pages)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        parts: list[tuple[str, int, int]] = []
        if starts[0][1] > 0:
            parts.append(("inicio", 0, starts[0][1]))
        for index, (title, start_page) in enumerate(starts):
            end_page = starts[index + 1][1] if index + 1 < len(starts) else total_pages
            if end_page > start_page:
                parts.append((title or "", start_page, end_page))

        output_paths = []
        first_number = 0 if starts[0][1] > 0 else 1
        for offset, (title, start_page, end_page) in enumerate(parts):
            number = first_number + offset
            safe_title = _sanitize_filename(title) or f"parte{number}"
            output_path = output_dir_path / f"{stem}_{number:02d}_{safe_title}.pdf"
            pages = list(range(start_page, end_page))
            write_pdf(pages_writer([(reader, pages)], copy_attachments=False), str(output_path))
            output_paths.append(str(output_path))

        return output_paths
