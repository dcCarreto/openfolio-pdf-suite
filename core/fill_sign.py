"""Preencher e assinar sem certificado (A04): texto, data, assinatura e iniciais desenhados
nas áreas marcadas, como conteúdo da página.

Diferente das anotações, o que é colocado aqui entra no conteúdo da página (como no
"Preencher e assinar" dos leitores ao salvar): não aparece na lista de comentários nem
some ao ocultá-los. Não é assinatura digital; para isso há a aba Assinatura digital.
"""

import io
from dataclasses import dataclass

from pypdf import PdfWriter
from reportlab.lib.utils import ImageReader

from .base import open_reader, require_valid_page_index, write_pdf
from .fonts import SANS, register_fonts, text_width
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay


@dataclass
class FillItem:
    """Um item a colocar: texto (ou data já formatada) ou imagem PNG/JPEG (assinatura,
    iniciais), ajustado à área sem distorcer."""

    page_index: int
    rect: tuple[float, float, float, float]  # espaço do usuário do PDF
    text: str = ""
    image: bytes = b""


def fit_text_size(text: str, width: float, height: float) -> float:
    """Tamanho da fonte do texto numa área: uma linha da altura da área, encolhida se não
    couber na largura. Vale em qualquer unidade (pontos no PDF, pixels na prévia)."""
    size = height * 0.7
    natural = text_width(text, SANS, size)
    if natural > width > 0:
        size *= width / natural
    return size


def _draw_item(canvas, geometry: PageGeometry, item: FillItem) -> None:
    left, bottom, right, top = geometry.user_rect_to_visual(item.rect)
    width, height = right - left, top - bottom
    if item.image:
        canvas.drawImage(
            ImageReader(io.BytesIO(item.image)),
            left,
            bottom,
            width,
            height,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        return
    size = fit_text_size(item.text, width, height)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(SANS, size)
    canvas.drawString(left, bottom + (height - size * 0.7) / 2, item.text)


class FillAndSign:
    def run(self, input_path: str, output_path: str, items: list[FillItem]) -> None:
        reader = open_reader(input_path)
        for item in items:
            require_valid_page_index(len(reader.pages), item.page_index)
        if not any(item.text.strip() or item.image for item in items):
            raise ValueError("Marque pelo menos uma área com texto, data, assinatura ou iniciais.")

        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)
        register_fonts()
        for page_index in sorted({item.page_index for item in items}):
            geometry = PageGeometry.from_pypdf_page(reader.pages[page_index])
            page_items = [item for item in items if item.page_index == page_index and (item.text.strip() or item.image)]

            def draw(canvas, _width, _height, page_items=page_items, geometry=geometry):
                for item in page_items:
                    _draw_item(canvas, geometry, item)

            if (overlay := visual_overlay(geometry, draw)) is not None:
                writer.pages[page_index].merge_page(overlay)
        write_pdf(writer, output_path)
