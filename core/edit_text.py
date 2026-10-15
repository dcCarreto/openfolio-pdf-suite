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
também). Não tenta casar fonte/tamanho com o texto original — quem usa escolhe o tamanho do
texto novo.
"""

from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index, write_pdf
from .geometry import Rect
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


class EditTextArea(PDFOperation):
    """Cobre as áreas marcadas e desenha o texto novo de cada uma por cima, achatando as
    páginas afetadas em imagem (mesma técnica de `core/redaction.RedactDocument`)."""

    def run(self, input_path: str, output_path: str, edits: list[TextEditRect]) -> int:
        reader = open_reader(input_path)
        edits_by_page: dict[int, list[TextEditRect]] = {}
        for edit in edits:
            require_valid_page_index(len(reader.pages), edit.page_index)
            edits_by_page.setdefault(edit.page_index, []).append(edit)

        # Cópia completa do documento: só as páginas editadas mudam (ver
        # `rasterize.replace_with_image_page`); marcadores, anexos e o resto ficam.
        writer = PdfWriter(clone_from=reader)
        pages_edited = 0
        pdfium_doc = pdfium.PdfDocument(input_path)
        try:
            pdfium_doc.init_forms()
            for index in sorted(edits_by_page):
                page_edits = edits_by_page[index]
                image, geometry = render_visual_page(pdfium_doc[index], RASTER_SCALE)
                placed = []
                for edit in page_edits:
                    clipped = geometry.clip_user_rect((edit.left, edit.bottom, edit.right, edit.top))
                    if clipped is None:
                        continue  # fora da área visível: some ao achatar, não há o que cobrir
                    visual_rect = geometry.user_rect_to_visual(clipped)
                    fill_visual_rects(image, geometry, [visual_rect], _hex_to_rgb255(edit.cover_color))
                    placed.append((edit, visual_rect))

                new_page = image_page(image, geometry.width, geometry.height, _text_drawer(placed))
                replace_with_image_page(writer, index, new_page)
                pages_edited += 1
        finally:
            pdfium_doc.close()

        write_pdf(writer, output_path)
        return pages_edited


def _text_drawer(placed: list[tuple[TextEditRect, Rect]]):
    def draw(canvas) -> None:
        for edit, (left, bottom, _right, top) in placed:
            red, green, blue = _hex_to_rgb01(edit.text_color)
            canvas.setFillColorRGB(red, green, blue)
            canvas.setFont("Helvetica", edit.font_size)
            text_y = bottom + (top - bottom - edit.font_size) / 2 + 2
            canvas.drawString(left + 2, text_y, edit.new_text)

    return draw
