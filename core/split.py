"""Divisão de um arquivo PDF em múltiplos documentos.

Cada parte leva os metadados, as camadas e os rótulos de página das suas páginas, e os
marcadores e links que apontam para elas (ver `core/document.py`). Os anexos do documento
original não são copiados para cada parte.
"""

import io
import re
from pathlib import Path

from .base import open_reader, write_pdf
from .document import pages_writer
from .progress import Progress, ensure_progress
from .scan_cleanup import find_blank_pages


def _write_parts(input_path: str, reader, output_dir: str, groups: list[list[int]]) -> list[str]:
    """Um arquivo por grupo de páginas: <nome>_part01.pdf, <nome>_part02.pdf..."""
    stem = Path(input_path).stem
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    digits = len(str(len(groups)))  # part01..part12: a ordem alfabética bate com a do documento
    output_paths = []
    for part_number, pages in enumerate(groups, start=1):
        output_path = output_dir_path / f"{stem}_part{part_number:0{digits}d}.pdf"
        write_pdf(pages_writer([(reader, pages)], copy_attachments=False), str(output_path))
        output_paths.append(str(output_path))
    return output_paths


class SplitPDF:
    """Divide um PDF em partes de N páginas."""

    def run(
        self, input_path: str, output_dir: str, pages_per_file: int = 1
    ) -> list[str]:
        if pages_per_file < 1:
            raise ValueError("pages_per_file deve ser maior ou igual a 1.")
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        groups = [list(range(start, min(start + pages_per_file, total_pages))) for start in range(0, total_pages, pages_per_file)]
        return _write_parts(input_path, reader, output_dir, groups)


class SplitByRanges:
    """Um arquivo por grupo de páginas (índices a partir de 0, na ordem dada): extrair as
    páginas selecionadas é um grupo só."""

    def run(self, input_path: str, output_dir: str, groups: list[list[int]]) -> list[str]:
        groups = [group for group in groups if group]
        if not groups:
            raise ValueError("Informe as páginas de cada arquivo.")
        reader = open_reader(input_path)
        total = len(reader.pages)
        if not all(0 <= index < total for group in groups for index in group):
            raise ValueError(f"O documento tem {total} página(s): confira as páginas informadas.")
        return _write_parts(input_path, reader, output_dir, groups)


class SplitBySize:
    """Partes de até `max_bytes`, com as páginas na ordem. Uma página que sozinha passa do
    limite fica num arquivo próprio (não há como reduzi-la aqui; a aba Comprimir reduz)."""

    def run(self, input_path: str, output_dir: str, max_bytes: int, progress: Progress | None = None) -> list[str]:
        if max_bytes < 1:
            raise ValueError("max_bytes deve ser maior ou igual a 1.")
        progress = ensure_progress(progress)
        reader = open_reader(input_path)
        total = len(reader.pages)

        def fits(start: int, end: int) -> bool:
            # O tamanho de verdade (recursos como fontes são compartilhados entre as páginas,
            # então não dá para somar as páginas uma a uma).
            buffer = io.BytesIO()
            pages_writer([(reader, list(range(start, end)))], copy_attachments=False).write(buffer)
            return buffer.tell() <= max_bytes

        groups: list[list[int]] = []
        start = 0
        while start < total:
            progress.update(start, total, "Medindo as partes")
            good = start + 1  # uma página vai sempre, mesmo passando do limite
            if fits(start, good):
                # Dobra o tamanho da parte até passar do limite, depois busca o ponto exato.
                bad, step = None, 1
                while good < total:
                    candidate = min(total, good + step)
                    if not fits(start, candidate):
                        bad = candidate
                        break
                    good, step = candidate, step * 2
                while bad is not None and bad - good > 1:
                    middle = (good + bad) // 2
                    if fits(start, middle):
                        good = middle
                    else:
                        bad = middle
            groups.append(list(range(start, good)))
            start = good
        progress.update(total, total, "Gravando")
        return _write_parts(input_path, reader, output_dir, groups)


class SplitAtBlankPages:
    """Divide nas páginas em branco (folhas de separação no scanner), que não vão para as
    partes; páginas em branco seguidas não criam partes vazias."""

    def run(self, input_path: str, output_dir: str, progress: Progress | None = None) -> list[str]:
        reader = open_reader(input_path)
        blanks = set(find_blank_pages(input_path, progress))
        if not blanks:
            raise ValueError("Nenhuma página em branco encontrada: não há onde dividir.")
        groups: list[list[int]] = [[]]
        for index in range(len(reader.pages)):
            if index in blanks:
                groups.append([])
            else:
                groups[-1].append(index)
        groups = [group for group in groups if group]
        if not groups:
            raise ValueError("Todas as páginas parecem em branco; nada foi alterado.")
        return _write_parts(input_path, reader, output_dir, groups)


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
