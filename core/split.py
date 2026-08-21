"""Divisão de um arquivo PDF em múltiplos documentos."""

import re
from pathlib import Path

from pypdf import PdfWriter

from .base import PDFOperation, open_reader


class SplitPDF(PDFOperation):
    """Divide um PDF em partes conforme os critérios informados."""

    def run(
        self, input_path: str, output_dir: str, pages_per_file: int = 1
    ) -> list[str]:
        if pages_per_file < 1:
            raise ValueError("pages_per_file deve ser maior ou igual a 1.")
        reader = open_reader(input_path)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        total_pages = len(reader.pages)
        for start in range(0, total_pages, pages_per_file):
            end = min(start + pages_per_file, total_pages)
            writer = PdfWriter()
            for page_index in range(start, end):
                writer.add_page(reader.pages[page_index])

            part_number = start // pages_per_file + 1
            output_path = output_dir_path / f"{stem}_part{part_number}.pdf"
            with open(output_path, "wb") as f:
                writer.write(f)
            output_paths.append(str(output_path))

        return output_paths


def _sanitize_filename(text: str) -> str:
    safe = re.sub(r"[^\w\-. ]", "_", text).strip()
    return safe[:60]


class SplitByBookmarks(PDFOperation):
    """Divide um PDF em um arquivo por marcador de nível superior do sumário (outline):
    cada arquivo vai da página do marcador até a página anterior ao próximo marcador de
    nível superior (ou até o fim do documento, no último). Marcadores aninhados (subtópicos)
    não geram corte — só o nível superior do sumário divide o documento, pra não fatiar um
    PDF em dezenas de arquivos de uma única página quando o sumário é bem detalhado."""

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

        output_paths = []
        for index, (title, start_page) in enumerate(starts):
            end_page = starts[index + 1][1] if index + 1 < len(starts) else total_pages
            if end_page <= start_page:
                continue
            writer = PdfWriter()
            for page_index in range(start_page, end_page):
                writer.add_page(reader.pages[page_index])

            safe_title = _sanitize_filename(title) or f"parte{index + 1}"
            output_path = output_dir_path / f"{stem}_{index + 1:02d}_{safe_title}.pdf"
            with open(output_path, "wb") as f:
                writer.write(f)
            output_paths.append(str(output_path))

        return output_paths
