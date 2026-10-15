"""Desenho por cima das páginas (marca d'água, numeração, cabeçalho/rodapé, texto do OCR).

O desenho é feito no espaço visual — a página como aparece na tela, com origem no canto
inferior esquerdo da área visível — e convertido para o espaço do usuário pela matriz da
geometria da página. Assim, "rodapé centralizado" fica no rodapé e de pé também em páginas
com `/Rotate` ou CropBox deslocada, em vez de ir parar na lateral, deitado.
"""

import io
from collections.abc import Callable

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import NameObject, RectangleObject
from reportlab.pdfgen import canvas as rl_canvas

from .geometry import PageGeometry

# Atributos de página que podem ser herdados dos nós da árvore de páginas.
_INHERITABLE = ("/Resources", "/MediaBox", "/CropBox", "/Rotate")

Draw = Callable[[rl_canvas.Canvas, float, float], bool | None]


def visual_overlay(geometry: PageGeometry, draw: Draw) -> PageObject | None:
    """Página com o que `draw(canvas, largura, altura)` desenhar em coordenadas visuais,
    pronta para `merge_page`. Se `draw` devolver False (nada a desenhar), devolve None."""
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(geometry.width, geometry.height))
    canvas.transform(*geometry.visual_to_user_matrix())
    if draw(canvas, geometry.width, geometry.height) is False:
        return None
    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    overlay = PdfReader(buffer).pages[0]
    # `merge_page` recorta o conteúdo mesclado pela CropBox da página sobreposta: com a
    # mesma área visível da página de destino, nada é cortado fora de lugar.
    overlay.mediabox = RectangleObject(geometry.box)
    overlay.cropbox = RectangleObject(geometry.box)
    return overlay


def materialize_inherited_attributes(writer: PdfWriter) -> None:
    """Copia para cada página os atributos que ela herda dos nós pais (recursos, caixas,
    rotação). Depois de `PdfWriter(clone_from=...)` a árvore de páginas fica como no
    original, e alterar uma página que herda `/Resources` (com `merge_page`, por exemplo)
    poderia deixá-la sem as fontes e imagens que o conteúdo dela usa."""
    for page in writer.pages:
        for key in _INHERITABLE:
            if key in page:
                continue
            value = _inherited_value(page, key)
            if value is not None:
                page[NameObject(key)] = value


def _inherited_value(page, key: str):
    visited: set[int] = set()
    parent = page.get("/Parent")
    while parent is not None:
        node = parent.get_object()
        if id(node) in visited:
            return None
        visited.add(id(node))
        if key in node:
            return node.raw_get(key)
        parent = node.get("/Parent")
    return None
