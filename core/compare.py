"""Comparação de duas versões de um PDF: diff de texto por página, diff visual e diff de
texto do documento inteiro com a posição das palavras (comparação lado a lado)."""

import difflib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageStat

from .base import EXTRACT, READ, open_pdfium, open_reader
from .progress import PDFIUM_LOCK, Progress, ensure_progress

_DIFF_SCALE = 1.5
_DIFF_THRESHOLD = 30  # diferença de luminância (0-255) a partir da qual um pixel conta como "mudou"
_HIGHLIGHT_ALPHA = 0.6


@dataclass
class PageTextDiff:
    page_index: int
    changed: bool
    diff_lines: list[str] = field(default_factory=list)


class CompareText:
    """Compara o texto de duas versões de um PDF, página a página, usando `difflib` (a
    mesma lógica de diff de texto da biblioteca padrão do Python, sem reinventar nada)."""

    def run(self, path_a: str, path_b: str, progress: Progress | None = None) -> list[PageTextDiff]:
        progress = ensure_progress(progress)
        reader_a = open_reader(path_a, purpose=EXTRACT)
        reader_b = open_reader(path_b, purpose=EXTRACT)
        total_pages = max(len(reader_a.pages), len(reader_b.pages))

        results = []
        for index in progress.steps(range(total_pages), total_pages, "Comparando páginas"):
            text_a = reader_a.pages[index].extract_text() if index < len(reader_a.pages) else ""
            text_b = reader_b.pages[index].extract_text() if index < len(reader_b.pages) else ""
            diff_lines = list(
                difflib.unified_diff(
                    text_a.splitlines(),
                    text_b.splitlines(),
                    fromfile="A",
                    tofile="B",
                    lineterm="",
                )
            )
            results.append(
                PageTextDiff(page_index=index, changed=bool(diff_lines), diff_lines=diff_lines)
            )
        return results


class Box(NamedTuple):
    """Retângulo numa página, no espaço do usuário do PDF (o do pdfium e do visualizador)."""

    page: int
    left: float
    bottom: float
    right: float
    top: float


@dataclass
class TextChange:
    kind: str  # "changed" | "removed" | "added"
    text_a: str
    text_b: str
    boxes_a: list[Box]  # uma caixa por linha do trecho; vazia quando o trecho não existe em A
    boxes_b: list[Box]
    anchor_a: Box | None  # onde a mudança fica em A ("added": a palavra vizinha), para rolar até ela
    anchor_b: Box | None


@dataclass
class DocumentDiff:
    changes: list[TextChange]
    # Palavras iguais nas duas versões (no máximo uma por linha): é por elas que a rolagem de
    # um lado acompanha a do outro, mesmo com o texto escorrido para outra página.
    matches: list[tuple[Box, Box]]
    pages_without_text_a: list[int]
    pages_without_text_b: list[int]


_KINDS = {"replace": "changed", "delete": "removed", "insert": "added"}
_FURNITURE_BAND = 0.15  # fração da altura da página, em cima e embaixo, onde ficam cabeçalho e rodapé


def _page_words(document, index: int) -> tuple[list[tuple[str, Box]], tuple[float, float]]:
    """As palavras da página (trechos entre espaços e quebras de linha) com a caixa de cada
    uma, e a base e o topo da página."""
    words: list[tuple[str, Box]] = []
    chars: list[str] = []
    boxes: list[tuple[float, float, float, float]] = []

    def flush():
        if chars:
            words.append((
                "".join(chars),
                Box(index, min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes)),
            ))
            chars.clear()
            boxes.clear()

    page = document[index]
    textpage = page.get_textpage()
    try:
        left, bottom, right, top = page.get_bbox()
        for char_index in range(textpage.count_chars()):
            char = chr(pdfium.raw.FPDFText_GetUnicode(textpage.raw, char_index))
            if char.isspace():  # inclui o \r\n que o pdfium gera no fim da linha
                flush()
            elif unicodedata.category(char) not in ("Cc", "Cf", "Cs"):  # hífen invisível etc.: some
                box = textpage.get_charbox(char_index)
                # Texto fora da área visível não conta: o Qt, por exemplo, repete fora da
                # página a linha de uma tabela que passa para a página seguinte.
                if left <= (box[0] + box[2]) / 2 <= right and bottom <= (box[1] + box[3]) / 2 <= top:
                    chars.append(char)
                    boxes.append(box)
        flush()
    finally:
        textpage.close()
        page.close()
    return words, (bottom, top)


def _same_line(last: Box, box: Box) -> bool:
    """Se `box` continua a linha de `last` (mesma página, mais à direita, alturas sobrepostas)."""
    return (
        last.page == box.page
        and box.left >= last.left
        and min(last.top, box.top) - max(last.bottom, box.bottom)
        > 0.5 * min(last.top - last.bottom, box.top - box.bottom)
    )


def _line_boxes(boxes: list[Box]) -> list[Box]:
    """Junta as caixas de palavras seguidas na mesma linha numa caixa só."""
    lines: list[Box] = []
    for box in boxes:
        last = lines[-1] if lines else None
        if last is not None and _same_line(last, box):
            lines[-1] = Box(box.page, last.left, min(last.bottom, box.bottom),
                            max(last.right, box.right), max(last.top, box.top))
        else:
            lines.append(box)
    return lines


def _without_page_furniture(
    pages: list[list[tuple[str, Box]]], extents: list[tuple[float, float]]
) -> list[list[tuple[str, Box]]]:
    """Tira cabeçalhos e rodapés. Depois que o texto escorre, o número da página cai no meio
    de outro trecho, e cada página viraria uma diferença.

    É cabeçalho ou rodapé a linha mais de fora da página (ou logo depois de outra que já é),
    perto da borda, que se repete na mesma altura em pelo menos 3 páginas e metade delas,
    com o mesmo texto a não ser pelo número da página ou o total ("Página 3 de 9"). Outros
    números contam: "Cláusula 2ª" no topo de uma página e "Cláusula 5ª" no de outra são
    texto, não cabeçalho.

    shortcut: a faixa é medida no espaço do usuário, então numa página com /Rotate ela fica
    nas laterais; trocar pela geometria visual se aparecerem escaneados girados com rodapé.
    """
    total = len(pages)
    edges: list[tuple[list, list]] = []  # por página: linhas do topo para dentro, do pé para dentro
    for page_index, (words, (bottom, top)) in enumerate(zip(pages, extents)):
        band = (top - bottom) * _FURNITURE_BAND
        lines: list[list[int]] = []
        for word_index, (_text, box) in enumerate(words):
            if lines and _same_line(words[lines[-1][-1]][1], box):
                lines[-1].append(word_index)
            else:
                lines.append([word_index])
        numbers = {str(page_index + 1), str(total)}
        keyed = []
        for line in lines:
            center = sum(words[i][1].bottom + words[i][1].top for i in line) / (2 * len(line))
            text = re.sub(
                r"(?<![^\W\d_])\d+(?![^\W\d_])",  # números soltos, não colados a letras ("2ª")
                lambda match: "#" if match.group() in numbers else match.group(),  # noqa: B023 (usada na hora)
                " ".join(words[i][0] for i in line),
            )
            keyed.append((center, (text, round(center / 4)), line))
        keyed.sort(key=lambda item: -item[0])
        edges.append((
            [item for item in keyed if item[0] > top - band],
            [item for item in reversed(keyed) if item[0] < bottom + band],
        ))

    minimum = max(3, (total + 1) // 2)
    dropped: dict[int, set[int]] = defaultdict(set)
    for side in (0, 1):
        position = [0] * total
        while True:
            keys = {
                page_index: edges[page_index][side][position[page_index]][1]
                for page_index in range(total)
                if position[page_index] < len(edges[page_index][side])
            }
            counts = Counter(keys.values())
            repeated = [page_index for page_index, key in keys.items() if counts[key] >= minimum]
            if not repeated:
                break
            for page_index in repeated:
                dropped[page_index].update(edges[page_index][side][position[page_index]][2])
                position[page_index] += 1
    return [
        [word for word_index, word in enumerate(words) if word_index not in dropped[page_index]]
        for page_index, words in enumerate(pages)
    ]


class CompareDocuments:
    """Compara o texto do documento inteiro, palavra a palavra, e diz onde fica cada
    diferença nas duas versões.

    Ao contrário de `CompareText`, que compara página com página, o texto das versões é
    comparado de uma vez: um parágrafo incluído na página 2 empurra o resto do texto para
    as páginas seguintes, e nada disso conta como mudança — só o parágrafo.
    """

    def run(self, path_a: str, path_b: str, progress: Progress | None = None) -> DocumentDiff:
        progress = ensure_progress(progress)
        open_reader(path_a, purpose=EXTRACT)  # recusa, com mensagem clara, PDF que não abre
        open_reader(path_b, purpose=EXTRACT)
        with PDFIUM_LOCK:
            doc_a = open_pdfium(path_a)
            doc_b = open_pdfium(path_b)
        pages_a: list[tuple[list[tuple[str, Box]], tuple[float, float]]] = []
        pages_b: list[tuple[list[tuple[str, Box]], tuple[float, float]]] = []
        try:
            with PDFIUM_LOCK:
                sides = [(doc_a, pages_a, index) for index in range(len(doc_a))]
                sides += [(doc_b, pages_b, index) for index in range(len(doc_b))]
            for document, pages, index in progress.steps(sides, len(sides), "Lendo o texto"):
                with PDFIUM_LOCK:
                    pages.append(_page_words(document, index))
        finally:
            with PDFIUM_LOCK:
                doc_a.close()
                doc_b.close()

        progress.update(0, 0, "Comparando o texto")

        def document_words(pages):
            kept = _without_page_furniture([words for words, _extent in pages], [extent for _words, extent in pages])
            return [word for page in kept for word in page]

        words_a, words_b = document_words(pages_a), document_words(pages_b)
        texts_a = [text for text, _box in words_a]
        texts_b = [text for text, _box in words_b]
        boxes_a = [box for _text, box in words_a]
        boxes_b = [box for _text, box in words_b]

        def anchor(boxes: list[Box], start: int, end: int) -> Box | None:
            if start < end:
                return boxes[start]
            if start > 0:
                return boxes[start - 1]  # o trecho entraria logo depois da palavra anterior
            return boxes[0] if boxes else None

        changes: list[TextChange] = []
        matches: list[tuple[Box, Box]] = []
        last_line = None
        # Com o autojunk (o padrão), palavras muito comuns ("de", "que") não servem de âncora: 12x
        # mais rápido num documento de 40 mil palavras. As operações continuam levando A a B,
        # então nenhuma diferença se perde; no pior caso, um trecho marcado sai maior.
        matcher = difflib.SequenceMatcher(None, texts_a, texts_b)
        for tag, a1, a2, b1, b2 in matcher.get_opcodes():
            progress.check()
            if tag == "equal":
                for box_a, box_b in zip(boxes_a[a1:a2], boxes_b[b1:b2]):
                    line = (box_a.page, round(box_a.top), box_b.page, round(box_b.top))
                    if line != last_line:
                        matches.append((box_a, box_b))
                        last_line = line
                continue
            changes.append(
                TextChange(
                    kind=_KINDS[tag],
                    text_a=" ".join(texts_a[a1:a2]),
                    text_b=" ".join(texts_b[b1:b2]),
                    boxes_a=_line_boxes(boxes_a[a1:a2]),
                    boxes_b=_line_boxes(boxes_b[b1:b2]),
                    anchor_a=anchor(boxes_a, a1, a2),
                    anchor_b=anchor(boxes_b, b1, b2),
                )
            )
        return DocumentDiff(
            changes=changes,
            matches=matches,
            pages_without_text_a=[index for index, (words, _extent) in enumerate(pages_a) if not words],
            pages_without_text_b=[index for index, (words, _extent) in enumerate(pages_b) if not words],
        )


@dataclass
class VisualDiffResult:
    page_index: int
    status: str  # "compared" | "only_in_a" | "only_in_b" | "size_mismatch"
    changed_fraction: float | None = None
    output_path: str | None = None


def _highlight_diff(image_a: Image.Image, image_b: Image.Image) -> tuple[Image.Image, float]:
    diff = ImageChops.difference(image_a, image_b).convert("L")
    mask = diff.point(lambda pixel: 255 if pixel > _DIFF_THRESHOLD else 0)
    changed_fraction = ImageStat.Stat(mask).mean[0] / 255.0

    red_layer = Image.new("RGB", image_b.size, (255, 0, 0))
    highlighted = Image.composite(red_layer, image_b, mask)
    highlighted = Image.blend(image_b, highlighted, _HIGHLIGHT_ALPHA)
    return highlighted, changed_fraction


class CompareVisual:
    """Gera uma imagem por página destacando em vermelho as diferenças visuais entre duas
    versões de um PDF (renderizadas via `pypdfium2`, já usado em `core/convert.py` e
    `core/redaction.py`). Páginas que só existem numa das versões, ou com tamanhos
    diferentes entre as versões, não geram imagem de diff — só são sinalizadas no
    resultado, para não produzir uma comparação enganosa pixel a pixel entre páginas que
    não correspondem uma à outra."""

    def run(
        self,
        path_a: str,
        path_b: str,
        output_dir: str,
        scale: float = _DIFF_SCALE,
        progress: Progress | None = None,
    ) -> list[VisualDiffResult]:
        open_reader(path_a, purpose=READ)  # recusa, com mensagem clara, PDF que não abre
        open_reader(path_b, purpose=READ)
        with PDFIUM_LOCK:
            doc_a = open_pdfium(path_a)
            doc_b = open_pdfium(path_b)
        try:
            return self._compare(doc_a, doc_b, output_dir, scale, ensure_progress(progress))
        finally:
            with PDFIUM_LOCK:
                doc_a.close()
                doc_b.close()

    def _compare(self, doc_a, doc_b, output_dir: str, scale: float, progress: Progress) -> list[VisualDiffResult]:
        with PDFIUM_LOCK:
            pages_a, pages_b = len(doc_a), len(doc_b)
        total_pages = max(pages_a, pages_b)

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = []
        for index in progress.steps(range(total_pages), total_pages, "Comparando páginas"):
            if index >= pages_a:
                results.append(VisualDiffResult(page_index=index, status="only_in_b"))
                continue
            if index >= pages_b:
                results.append(VisualDiffResult(page_index=index, status="only_in_a"))
                continue

            with PDFIUM_LOCK:
                image_a = doc_a[index].render(scale=scale).to_pil().convert("RGB")
                image_b = doc_b[index].render(scale=scale).to_pil().convert("RGB")
            if image_a.size != image_b.size:
                results.append(VisualDiffResult(page_index=index, status="size_mismatch"))
                continue

            highlighted, changed_fraction = _highlight_diff(image_a, image_b)
            output_path = output_dir_path / f"diff_page{index + 1}.png"
            highlighted.save(output_path)
            results.append(
                VisualDiffResult(
                    page_index=index,
                    status="compared",
                    changed_fraction=changed_fraction,
                    output_path=str(output_path),
                )
            )

        return results
