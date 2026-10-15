"""Achatamento de páginas em imagem, usado pela redação e pela edição de texto.

A página é renderizada como aparece na tela (o pdfium já aplica a CropBox e o `/Rotate`),
as áreas marcadas são pintadas **nos próprios pixels** e a página é trocada por uma página
nova contendo só essa imagem — no tamanho visual e sem `/Rotate`, então visualmente idêntica
à original.

Pintar nos pixels é o que torna a remoção definitiva. Desenhar um retângulo por cima da
imagem (como era feito antes) só esconde o conteúdo: a imagem embutida continua com o texto
original e qualquer extrator de imagens o recupera. E como só a área visível é renderizada,
nada que estava fora da CropBox (escondido, mas presente no arquivo) sobrevive.
"""

import io
from collections.abc import Callable, Iterable

from PIL import Image, ImageDraw
from pypdf import PageObject, PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .geometry import PageGeometry, Rect

RASTER_SCALE = 300 / 72  # 300 DPI, a mesma resolução usada no OCR


def render_visual_page(pdfium_page, scale: float = RASTER_SCALE) -> tuple[Image.Image, PageGeometry]:
    """Renderiza a página como o usuário a vê e devolve a imagem com a geometria dela."""
    geometry = PageGeometry.from_pdfium_page(pdfium_page)
    image = pdfium_page.render(scale=scale).to_pil().convert("RGB")
    return image, geometry


def visible_visual_rects(geometry: PageGeometry, user_rects: Iterable[Rect]) -> list[Rect]:
    """Converte áreas do espaço do usuário para o espaço visual, descartando o que cai fora
    da área visível — essa parte já desaparece ao achatar a página."""
    result = []
    for rect in user_rects:
        clipped = geometry.clip_user_rect(rect)
        if clipped is not None:
            result.append(geometry.user_rect_to_visual(clipped))
    return result


def fill_visual_rects(
    image: Image.Image, geometry: PageGeometry, visual_rects: Iterable[Rect], color: tuple[int, int, int]
) -> None:
    """Pinta as áreas (espaço visual) diretamente nos pixels da imagem da página."""
    draw = ImageDraw.Draw(image)
    for rect in visual_rects:
        x0, y0, x1, y1 = geometry.visual_rect_to_pixels(rect, image.width, image.height)
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=color)


def image_page(
    image: Image.Image,
    width: float,
    height: float,
    draw_over: Callable[[rl_canvas.Canvas], None] | None = None,
) -> PageObject:
    """Monta uma página PDF de `width` x `height` pontos contendo só a imagem.

    `draw_over(canvas)`, se informado, desenha por cima da imagem em coordenadas visuais (a
    edição de texto escreve o texto novo assim, como texto de verdade e pesquisável).
    """
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(width, height))
    canvas.drawImage(ImageReader(image), 0, 0, width=width, height=height)
    if draw_over is not None:
        draw_over(canvas)
    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]
