""""Edição" de texto num PDF: cobre uma área da página e desenha um texto novo por cima.

PDF não guarda texto como um documento de processador de texto — cada trecho é um conjunto
de operadores de posicionamento de glifo dentro do content stream, amarrado à fonte
original (que pode nem estar embutida). Editar essa estrutura preservando fonte, kerning e
reflow é o tipo de cirurgia que ferramentas comerciais resolvem com motores próprios bem
mais sofisticados que qualquer coisa razoável de escrever aqui — e um acerto sutilmente
errado deixaria o PDF corrompido ou o texto antigo ainda recuperável por baixo, a mesma
categoria de risco que `core/redaction.py` já evita usando rasterização em vez de editar o
content stream na mão (ver o comentário lá). Por isso esta ferramenta reaproveita
exatamente a técnica da redação (`core/rasterize.py`) — rasterizar a página inteira e pintar
a área marcada nos próprios pixels, de modo que o texto antigo não sobreviva nem na imagem —
e adiciona só um passo: desenhar o texto novo por cima, como texto de verdade.

O resultado é uma edição visual, não uma edição do objeto de texto original: a página
inteira perde a camada de texto pesquisável original, igual à redação (documentado lá
também). Não tenta casar fonte/tamanho com o texto original — quem usa escolhe a fonte
(entre as embutidas em `core/fonts.py`), o tamanho e as cores do texto novo.

O texto quebra linha para caber na largura da área (e respeita as quebras de linha
digitadas). As linhas que não cabem na altura da área não são desenhadas — nem como texto
invisível — e a área aparece em `EditTextResult.clipped`, para a interface avisar.
"""

from dataclasses import dataclass, field

import pypdfium2 as pdfium
from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index, write_pdf
from .fonts import MONO, SANS, SANS_BOLD, register_fonts, wrap_text
from .geometry import Rect
from .progress import PDFIUM_LOCK, Progress, ensure_progress
from .rasterize import (
    RASTER_SCALE,
    fill_visual_rects,
    image_page,
    render_visual_page,
    replace_with_image_page,
)


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _hex_to_rgb255(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


@dataclass
class TextEditRect:
    """Uma área marcada para "cobrir e reescrever", no espaço do usuário do PDF (o mesmo de
    `/Rect` e do pdfium — sem `/Rotate` nem CropBox aplicados)."""

    page_index: int
    left: float
    bottom: float
    right: float
    top: float
    new_text: str
    font_size: float = 12
    text_color: str = "000000"
    cover_color: str = "ffffff"
    font: str = "sans"  # uma das chaves de EDIT_FONTS


EDIT_FONTS = {"sans": SANS, "sans-bold": SANS_BOLD, "mono": MONO}
_PADDING = 2
_LINE_SPACING = 1.2


@dataclass
class EditTextResult:
    pages_edited: int
    # Áreas (pela posição na lista recebida, a partir de 0) em que o texto não coube todo.
    clipped: list[int] = field(default_factory=list)


class EditTextArea(PDFOperation):
    """Cobre as áreas marcadas e desenha o texto novo de cada uma por cima, achatando as
    páginas afetadas em imagem (mesma técnica de `core/redaction.RedactDocument`)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        edits: list[TextEditRect],
        progress: Progress | None = None,
    ) -> EditTextResult:
        progress = ensure_progress(progress)
        reader = open_reader(input_path)
        edits_by_page: dict[int, list[tuple[int, TextEditRect]]] = {}
        for number, edit in enumerate(edits):
            require_valid_page_index(len(reader.pages), edit.page_index)
            if edit.font not in EDIT_FONTS:
                raise ValueError(f"Fonte inválida: {edit.font}")
            edits_by_page.setdefault(edit.page_index, []).append((number, edit))
        register_fonts()
        clipped_areas: list[int] = []

        # Cópia completa do documento: só as páginas editadas mudam (ver
        # `rasterize.replace_with_image_page`); marcadores, anexos e o resto ficam.
        writer = PdfWriter(clone_from=reader)
        pages_edited = 0
        with PDFIUM_LOCK:
            pdfium_doc = pdfium.PdfDocument(input_path)
            pdfium_doc.init_forms()
        try:
            for index in progress.steps(sorted(edits_by_page), message="Editando páginas"):
                page_edits = edits_by_page[index]
                with PDFIUM_LOCK:
                    image, geometry = render_visual_page(pdfium_doc[index], RASTER_SCALE)
                placed = []
                for number, edit in page_edits:
                    clipped = geometry.clip_user_rect((edit.left, edit.bottom, edit.right, edit.top))
                    if clipped is None:
                        continue  # fora da área visível: some ao achatar, não há o que cobrir
                    visual_rect = geometry.user_rect_to_visual(clipped)
                    fill_visual_rects(image, geometry, [visual_rect], _hex_to_rgb255(edit.cover_color))
                    lines, fits = layout_text(edit, visual_rect)
                    if not fits:
                        clipped_areas.append(number)
                    placed.append((edit, visual_rect, lines))

                new_page = image_page(image, geometry.width, geometry.height, _text_drawer(placed))
                replace_with_image_page(writer, index, new_page)
                pages_edited += 1
        finally:
            with PDFIUM_LOCK:
                pdfium_doc.close()

        write_pdf(writer, output_path)
        return EditTextResult(pages_edited=pages_edited, clipped=sorted(clipped_areas))


def layout_text(edit: TextEditRect, visual_rect: Rect) -> tuple[list[tuple[str, float, float]], bool]:
    """Linhas do texto novo prontas para desenhar — (texto, x, y da linha de base) no espaço
    visual — e se todas couberam na área. O bloco fica centralizado na vertical quando cabe;
    quando não cabe, começa no topo e as linhas que passariam da base ficam de fora."""
    left, bottom, right, top = visual_rect
    font = EDIT_FONTS[edit.font]
    size = edit.font_size
    lines = wrap_text(edit.new_text, font, size, max(1.0, right - left - 2 * _PADDING))
    while lines and not lines[-1].strip():
        lines.pop()
    line_height = size * _LINE_SPACING
    height = top - bottom
    block_height = len(lines) * line_height
    fits = block_height <= height + 0.01 or len(lines) <= 1
    block_top = bottom + (height + block_height) / 2 if fits else top
    placed = []
    for index, line in enumerate(lines):
        line_top = block_top - index * line_height
        baseline = line_top - (line_height + size * 0.7) / 2
        if not fits and baseline - size * 0.25 < bottom:
            break
        placed.append((line, left + _PADDING, baseline))
    return placed, fits and len(placed) == len(lines)


def _text_drawer(placed):
    def draw(canvas) -> None:
        for edit, _rect, lines in placed:
            red, green, blue = _hex_to_rgb01(edit.text_color)
            canvas.setFillColorRGB(red, green, blue)
            canvas.setFont(EDIT_FONTS[edit.font], edit.font_size)
            for text, x, y in lines:
                canvas.drawString(x, y, text)

    return draw
