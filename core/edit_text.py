""""Edição" de texto num PDF: cobre uma área da página e desenha um texto novo por cima.

PDF não guarda texto como um documento de processador de texto — cada trecho é um conjunto
de operadores de posicionamento de glifo dentro do content stream, amarrado à fonte
original (que pode nem estar embutida). Editar essa estrutura preservando fonte, kerning e
reflow é o tipo de cirurgia que ferramentas comerciais resolvem com motores próprios bem
mais sofisticados que qualquer coisa razoável de escrever aqui — e um acerto sutilmente
errado deixaria o PDF corrompido ou o texto antigo ainda recuperável por baixo, a mesma
categoria de risco que `core/redaction.py` já evita usando rasterização em vez de editar o
content stream na mão (ver o comentário lá). Por isso esta ferramenta reaproveita
exatamente a técnica já validada da redação — rasterizar a página inteira e cobrir a área
marcada — e adiciona só um passo: desenhar o texto novo por cima da cobertura.

O resultado é uma edição visual, não uma edição do objeto de texto original: a página
inteira perde a camada de texto pesquisável, igual à redação (documentado lá também). Não
tenta casar fonte/tamanho com o texto original — quem usa escolhe a fonte e o tamanho do
texto novo.
"""

import io
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .base import PDFOperation, open_reader
from .redaction import _REDACT_SCALE


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


@dataclass
class TextEditRect:
    """Uma área marcada para "cobrir e reescrever", em pontos PDF (origem inferior-esquerda)."""

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
        edits_by_page: dict[int, list[TextEditRect]] = {}
        for edit in edits:
            edits_by_page.setdefault(edit.page_index, []).append(edit)

        reader = open_reader(input_path)
        pdfium_doc = pdfium.PdfDocument(input_path)
        writer = PdfWriter()
        pages_edited = 0

        for index, page in enumerate(reader.pages):
            page_edits = edits_by_page.get(index)
            if not page_edits:
                writer.add_page(page)
                continue

            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            image = pdfium_doc[index].render(scale=_REDACT_SCALE).to_pil()

            buffer = io.BytesIO()
            c = rl_canvas.Canvas(buffer, pagesize=(width, height))
            c.drawImage(ImageReader(image), 0, 0, width=width, height=height)
            for edit in page_edits:
                cover_r, cover_g, cover_b = _hex_to_rgb01(edit.cover_color)
                c.setFillColorRGB(cover_r, cover_g, cover_b)
                c.rect(
                    edit.left,
                    edit.bottom,
                    edit.right - edit.left,
                    edit.top - edit.bottom,
                    fill=1,
                    stroke=0,
                )

                text_r, text_g, text_b = _hex_to_rgb01(edit.text_color)
                c.setFillColorRGB(text_r, text_g, text_b)
                c.setFont("Helvetica", edit.font_size)
                text_y = edit.bottom + (edit.top - edit.bottom - edit.font_size) / 2 + 2
                c.drawString(edit.left + 2, text_y, edit.new_text)
            c.showPage()
            c.save()
            buffer.seek(0)

            writer.add_page(PdfReader(buffer).pages[0])
            pages_edited += 1

        with open(output_path, "wb") as f:
            writer.write(f)
        return pages_edited
