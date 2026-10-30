"""Marca d'água em arquivos PDF."""

import io
import math
import re

from pypdf import PageObject, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from .messages import DOC_PAGES, plural_message
from .base import open_reader, write_pdf
from .document import pages_writer
from .fonts import SANS_BOLD, register_fonts
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay

CENTER = "center"
TILE = "tile"
POSITIONS = (CENTER, "top-left", "top-right", "bottom-left", "bottom-right", TILE)
_MARGIN = 36  # meia polegada da borda, nos cantos


class AddWatermark:
    """Adiciona uma marca d'água de texto ou imagem às páginas de um PDF, girada em relação à
    página como ela aparece na tela (também em páginas com `/Rotate`).

    - `image_path`: um logotipo (PNG com transparência, JPEG...) no lugar do texto, com
      `image_width` como fração da largura da página.
    - `position`: o centro, um dos cantos (a marca girada inteira dentro da margem) ou
      "tile", repetida em mosaico pela página toda.
    - `behind`: por baixo do conteúdo, como um papel timbrado. Some atrás de páginas
      escaneadas, que são uma imagem opaca cobrindo a página.
    - `pages`: índices a partir de 0; None marca todas.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        text: str = "",
        opacity: float = 0.3,
        font_size: int = 40,
        rotation: float = 45,
        *,
        color: str = "000000",
        image_path: str | None = None,
        image_width: float = 0.3,
        position: str = CENTER,
        behind: bool = False,
        pages: list[int] | None = None,
    ) -> None:
        draw = _drawing(
            text=text,
            opacity=opacity,
            font_size=font_size,
            rotation=rotation,
            color=color,
            image_path=image_path,
            image_width=image_width,
            position=position,
        )
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        _apply(reader, writer, range(len(reader.pages)), draw, behind, pages)
        write_pdf(writer, output_path)


def watermark_preview(input_path: str, page_index: int, **options) -> bytes:
    """Só a página `page_index`, já com a marca d'água (as opções de `AddWatermark.run`),
    como um PDF na memória: a pré-visualização não grava nem copia o documento inteiro."""
    behind = options.pop("behind", False)
    options.pop("pages", None)
    draw = _drawing(**options)
    reader = open_reader(input_path)
    writer = pages_writer([(reader, [page_index])], copy_attachments=False)
    _apply(reader, writer, [page_index], draw, behind, None)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _apply(reader, writer: PdfWriter, source_indices, draw, behind: bool, pages: list[int] | None) -> None:
    total = len(reader.pages)
    if pages is not None and not pages:
        raise ValueError("Informe as páginas a marcar.")
    if pages is not None and not all(0 <= index < total for index in pages):
        raise ValueError(plural_message(total, *DOC_PAGES))
    chosen = set(range(total) if pages is None else pages)
    materialize_inherited_attributes(writer)
    # Uma sobreposição por geometria de página: o pypdf copia os recursos dela uma vez só,
    # e um logotipo não vira cem cópias num documento de cem páginas.
    overlays: dict[PageGeometry, PageObject | None] = {}
    for source_index, page in zip(source_indices, writer.pages):
        if source_index not in chosen:
            continue
        geometry = PageGeometry.from_pypdf_page(reader.pages[source_index])
        if geometry not in overlays:
            overlays[geometry] = visual_overlay(geometry, draw)
        if (overlay := overlays[geometry]) is not None:
            page.merge_page(overlay, over=not behind)


def _drawing(
    text: str = "",
    opacity: float = 0.3,
    font_size: int = 40,
    rotation: float = 45,
    color: str = "000000",
    image_path: str | None = None,
    image_width: float = 0.3,
    position: str = CENTER,
):
    """A função que desenha a marca numa página (para `visual_overlay`), já validada."""
    text = text.strip()
    if not text and not image_path:
        raise ValueError("Informe o texto ou a imagem da marca d'água.")
    if position not in POSITIONS:
        raise ValueError(f"Posição inválida: {position}")
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
        raise ValueError(f"Cor inválida (use hexadecimal, como ff0000): {color}")
    red, green, blue = (int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    image = None
    if image_path:
        try:
            image = ImageReader(image_path)
            pixel_width, pixel_height = image.getSize()
        except Exception as error:  # o reportlab embrulha os erros do Pillow de vários jeitos
            raise ValueError(f"Não foi possível ler a imagem {image_path}: {error}") from error
    else:
        register_fonts()

    def draw(canvas, width: float, height: float) -> None:
        if image is not None:
            item_width = width * image_width
            item_height = item_width * pixel_height / pixel_width
        else:
            item_width, item_height = stringWidth(text, SANS_BOLD, font_size), font_size * 0.7
        # A caixa da marca já girada, para encostar nos cantos sem sair da página.
        angle = math.radians(rotation)
        box_width = abs(item_width * math.cos(angle)) + abs(item_height * math.sin(angle))
        box_height = abs(item_width * math.sin(angle)) + abs(item_height * math.cos(angle))

        if position == TILE:
            step_x, step_y = box_width * 1.5, box_height * 1.5
            centers = [
                (x + (step_x / 2 if row % 2 else 0), y)
                for row, y in enumerate(_steps(height, step_y))
                for x in _steps(width + step_x, step_x)
            ]
        else:
            vertical, _, horizontal = position.partition("-")
            x = {"left": _MARGIN + box_width / 2, "right": width - _MARGIN - box_width / 2}.get(horizontal, width / 2)
            y = {"bottom": _MARGIN + box_height / 2, "top": height - _MARGIN - box_height / 2}.get(vertical, height / 2)
            centers = [(x, y)]

        canvas.setFillColor(Color(red, green, blue, alpha=opacity))
        canvas.setFillAlpha(opacity)  # a imagem usa a mesma opacidade do preenchimento
        if image is None:
            canvas.setFont(SANS_BOLD, font_size)
        for x, y in centers:
            canvas.saveState()
            canvas.translate(x, y)
            canvas.rotate(rotation)
            if image is not None:
                canvas.drawImage(image, -item_width / 2, -item_height / 2, item_width, item_height, mask="auto")
            else:
                canvas.drawCentredString(0, -item_height / 2, text)
            canvas.restoreState()

    return draw


def _steps(length: float, step: float) -> list[float]:
    """Posições a cada `step`, de antes do início até depois do fim (o mosaico cobre as bordas)."""
    count = int(length / step) + 2
    return [length / 2 + step * (i - count / 2) for i in range(count + 1)]
