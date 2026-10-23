"""Marcadores (sumário/outline) de navegação em arquivos PDF."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from pypdf import PdfWriter

from .base import READ, open_reader, require_valid_page_index, write_pdf
from .progress import Progress, ensure_progress


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


class SetOutline:
    """Troca o sumário do PDF pela árvore dada (a ordem dos itens, com o nível de cada um:
    um item de nível N+1 fica dentro do último de nível N).

    O sumário antigo sai do arquivo de verdade: um título apagado não fica escondido nos
    bytes, como ficaria se só deixasse de ser referenciado.

    shortcut: grava só título e página; cor, negrito, itálico e destinos que não são uma
    página deste documento (um link, outro arquivo) se perdem. Guardar a ação original de
    cada item quando ele não muda resolveria.
    """

    def run(self, input_path: str, output_path: str, items: list[OutlineItem]) -> None:
        reader = open_reader(input_path)
        previous = -1
        for item in items:
            if item.page_index is not None:
                require_valid_page_index(len(reader.pages), item.page_index)
            if not 0 <= item.level <= previous + 1:
                raise ValueError("Nível de marcador fora da hierarquia.")
            previous = item.level

        # Sai do documento lido antes da cópia, que leva só o que é alcançável: o sumário
        # velho (itens que apontam uns para os outros) não vai junto nem como objeto solto.
        if "/Outlines" in reader.root_object:
            del reader.root_object["/Outlines"]
        writer = PdfWriter(clone_from=reader)
        parents: list = []
        for item in items:
            del parents[item.level :]
            parent = parents[-1] if parents else None
            parents.append(writer.add_outline_item(item.title, item.page_index, parent=parent, is_open=False))
        write_pdf(writer, output_path)


_HEADING_RATIO = 1.15  # fonte pelo menos 15% maior que a do corpo do texto
_MAX_HEADING_CHARS = 120
_MAX_LEVELS = 3


class DetectHeadings:
    """Sugere um sumário a partir dos títulos: linhas curtas com fonte maior que a do
    corpo do texto (a mais usada no documento). Cada tamanho de título, do maior para o
    menor, vira um nível (até três).

    shortcut: só olha o tamanho da fonte; um título em negrito do mesmo tamanho do texto
    não é achado. A árvore de estrutura de um PDF marcado (H1, H2...) seria mais exata.
    """

    def run(self, input_path: str, progress: Progress | None = None) -> list[OutlineItem]:
        progress = ensure_progress(progress)
        reader = open_reader(input_path, purpose=READ)
        lines: list[tuple[int, float, str]] = []  # (página, tamanho, texto)
        body: Counter[float] = Counter()
        total = len(reader.pages)
        for index, page in enumerate(reader.pages):
            progress.update(index, total, "Procurando os títulos")
            for size, text in _page_lines(page):
                body[size] += len(text)
                lines.append((index, size, text))
        if not body:
            return []
        body_size = body.most_common(1)[0][0]
        headings = [
            (index, size, text)
            for index, size, text in lines
            if size >= body_size * _HEADING_RATIO and len(text) <= _MAX_HEADING_CHARS and re.search(r"[^\W\d_]", text)
        ]
        sizes = sorted({size for _index, size, _text in headings}, reverse=True)[:_MAX_LEVELS]
        items, previous = [], -1
        for index, size, text in headings:
            if size not in sizes:
                continue
            level = min(sizes.index(size), previous + 1)  # um subtítulo antes de um título fica no topo
            items.append(OutlineItem(level=level, title=text, page_index=index))
            previous = level
        return items


def _page_lines(page) -> list[tuple[float, str]]:
    """As linhas da página com o tamanho da fonte em que aparecem (já com as escalas das
    matrizes), na ordem do conteúdo."""
    chunks: list[tuple[float, float, str]] = []

    def visitor(text, cm, tm, _font, font_size):
        if not text.strip():
            return
        # A altura da fonte na página: o vetor vertical de Tm x CTM.
        c, d = tm[2] * cm[0] + tm[3] * cm[2], tm[2] * cm[1] + tm[3] * cm[3]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        chunks.append((round(y, 1), round(font_size * math.hypot(c, d), 1), text))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []  # página que o pypdf não lê: sem títulos dela
    lines: list[tuple[float, str]] = []
    last_key = None
    for y, size, text in chunks:
        if (y, size) == last_key:
            lines[-1] = (size, lines[-1][1] + text)
        else:
            lines.append((size, text))
            last_key = (y, size)
    return [(size, " ".join(text.split())) for size, text in lines if text.strip()]
