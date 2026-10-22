"""Marcadores (sumário/outline) de navegação em arquivos PDF."""

from dataclasses import dataclass

from pypdf import PdfWriter

from .base import READ, open_reader, require_valid_page_index, write_pdf


class AddBookmarks:
    """Adiciona marcadores de navegação (outline) a um PDF, depois dos que ele já tem."""

    def run(self, input_path: str, output_path: str, bookmarks: list[tuple[str, int]]) -> None:
        reader = open_reader(input_path)
        for _title, page_number in bookmarks:
            require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=reader)
        for title, page_number in bookmarks:
            writer.add_outline_item(title, page_number)
        write_pdf(writer, output_path)


@dataclass
class OutlineItem:
    level: int  # 0 = nível superior
    title: str
    page_index: int | None  # None se o destino não aponta para uma página deste documento


class ListOutline:
    """O sumário (marcadores) do PDF em ordem, com o nível de cada item e a página de
    destino — para o painel de marcadores do visualizador."""

    def run(self, input_path: str) -> list[OutlineItem]:
        reader = open_reader(input_path, purpose=READ)
        items: list[OutlineItem] = []

        def walk(entries, level: int, depth: int = 0) -> None:
            if depth > 64:
                return
            for entry in entries:
                if isinstance(entry, list):
                    walk(entry, level + 1, depth + 1)
                    continue
                try:
                    page = reader.get_destination_page_number(entry)
                except Exception:
                    page = None
                items.append(OutlineItem(level=level, title=str(entry.title or ""), page_index=page))

        try:
            walk(reader.outline, 0)
        except Exception:
            return items  # sumário malformado: o que deu para ler
        return items
