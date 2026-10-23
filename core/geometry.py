"""Geometria de página: conversão entre o espaço do usuário do PDF e o que aparece na tela.

Três referenciais convivem no app:

- **Espaço do usuário**: o sistema de coordenadas do próprio PDF — o do content stream, do
  `/Rect` das anotações e do `get_charbox` do pdfium. Não leva em conta `/Rotate` nem a
  CropBox, e a origem nem sempre é (0, 0).
- **Espaço visual**: a página como o usuário a vê — só a área visível (MediaBox ∩ CropBox),
  já girada pelo `/Rotate`. Origem no canto inferior esquerdo, y para cima, em pontos.
- **Tela**: o espaço visual multiplicado pela escala, com origem no canto superior esquerdo e
  y para baixo — o referencial dos pixels do visualizador e do bitmap que o pdfium renderiza.

Antes deste módulo, cada parte do app assumia que os três eram o mesmo (origem em (0, 0),
sem rotação). Isso só vale para páginas sem `/Rotate` e sem CropBox deslocada, e quebrava a
redação justamente nos escaneados girados: a tarja ia para um lugar e o texto ficava em
outro. As fórmulas seguem as do próprio pdfium (`CPDF_Page::UpdateDimensions`), para bater
exatamente com o que ele renderiza.
"""

import math
from dataclasses import dataclass

Rect =tuple[float, float, float, float]  # (left, bottom, right, top)
Matrix = tuple[float, float, float, float, float, float]  # [a b c d e f], como o operador `cm`


def normalize_rotation(rotation) -> int:
    """Normaliza um `/Rotate` do jeito do pdfium: múltiplos de 90, sentido horário, 0 a 270.

    Valores fora de múltiplos de 90 são inválidos pela especificação; o pdfium trunca a
    divisão (45 vira 0, -90 vira 270), e aqui fazemos igual para não divergir do render.
    """
    quarter_turns = int(float(rotation) / 90) % 4
    return quarter_turns * 90


def normalize_rect(rect) -> Rect:
    """Ordena as coordenadas de um retângulo (PDFs válidos podem guardá-las invertidas)."""
    x0, y0, x1, y1 = (float(value) for value in rect)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def intersect_rects(a: Rect, b: Rect) -> Rect | None:
    """Interseção de dois retângulos normalizados, ou None se não houver área em comum."""
    left, bottom = max(a[0], b[0]), max(a[1], b[1])
    right, top = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or top <= bottom:
        return None
    return (left, bottom, right, top)


@dataclass(frozen=True)
class PageGeometry:
    """Área visível de uma página (no espaço do usuário) e a rotação aplicada a ela."""

    box: Rect
    rotation: int = 0

    @classmethod
    def from_boxes(cls, mediabox, cropbox=None, rotation=0) -> "PageGeometry":
        media = normalize_rect(mediabox)
        visible = media
        if cropbox is not None:
            # Como o pdfium: a área visível é a interseção das duas caixas. Uma CropBox que
            # não toca a MediaBox é inválida; nesse caso fica só a MediaBox.
            visible = intersect_rects(media, normalize_rect(cropbox)) or media
        return cls(box=visible, rotation=normalize_rotation(rotation))

    @classmethod
    def from_pypdf_page(cls, page) -> "PageGeometry":
        # O pypdf já resolve a herança de MediaBox/CropBox/Rotate da árvore de páginas, e
        # `page.cropbox` cai na MediaBox quando a página não define uma.
        return cls.from_boxes(page.mediabox, page.cropbox, page.rotation)

    @classmethod
    def from_pdfium_page(cls, page) -> "PageGeometry":
        # `get_bbox()` já é a interseção MediaBox ∩ CropBox e, ao contrário de
        # `get_mediabox()`/`get_cropbox()`, herda caixas definidas nos nós pais.
        return cls(box=normalize_rect(page.get_bbox()), rotation=normalize_rotation(page.get_rotation()))

    @property
    def _box_size(self) -> tuple[float, float]:
        left, bottom, right, top = self.box
        return right - left, top - bottom

    @property
    def width(self) -> float:
        """Largura visual (já considerando a rotação), em pontos."""
        box_width, box_height = self._box_size
        return box_height if self.rotation in (90, 270) else box_width

    @property
    def height(self) -> float:
        """Altura visual (já considerando a rotação), em pontos."""
        box_width, box_height = self._box_size
        return box_width if self.rotation in (90, 270) else box_height

    # -- espaço do usuário <-> espaço visual ---------------------------------------------

    def user_to_visual(self, x: float, y: float) -> tuple[float, float]:
        left, bottom, right, top = self.box
        if self.rotation == 0:
            return (x - left, y - bottom)
        if self.rotation == 90:
            return (y - bottom, right - x)
        if self.rotation == 180:
            return (right - x, top - y)
        return (top - y, x - left)

    def visual_to_user(self, vx: float, vy: float) -> tuple[float, float]:
        left, bottom, right, top = self.box
        if self.rotation == 0:
            return (vx + left, vy + bottom)
        if self.rotation == 90:
            return (right - vy, vx + bottom)
        if self.rotation == 180:
            return (right - vx, top - vy)
        return (left + vy, top - vx)

    def visual_to_user_matrix(self) -> Matrix:
        """Matriz que leva coordenadas visuais ao espaço do usuário.

        Aplicada com `cm` (ou `canvas.transform` do reportlab) antes de desenhar, faz o
        conteúdo aparecer "de pé" e no lugar certo na página, qualquer que seja o `/Rotate`.
        """
        left, bottom, right, top = self.box
        if self.rotation == 0:
            return (1.0, 0.0, 0.0, 1.0, left, bottom)
        if self.rotation == 90:
            return (0.0, 1.0, -1.0, 0.0, right, bottom)
        if self.rotation == 180:
            return (-1.0, 0.0, 0.0, -1.0, right, top)
        return (0.0, -1.0, 1.0, 0.0, left, top)

    def user_rect_to_visual(self, rect: Rect) -> Rect:
        x0, y0 = self.user_to_visual(rect[0], rect[1])
        x1, y1 = self.user_to_visual(rect[2], rect[3])
        return normalize_rect((x0, y0, x1, y1))

    def visual_rect_to_user(self, rect: Rect) -> Rect:
        x0, y0 = self.visual_to_user(rect[0], rect[1])
        x1, y1 = self.visual_to_user(rect[2], rect[3])
        return normalize_rect((x0, y0, x1, y1))

    def clip_user_rect(self, rect: Rect) -> Rect | None:
        """Recorta um retângulo do espaço do usuário à área visível da página."""
        return intersect_rects(normalize_rect(rect), self.box)

    # -- espaço do usuário <-> tela ------------------------------------------------------

    def user_to_screen(self, x: float, y: float, scale: float) -> tuple[float, float]:
        vx, vy = self.user_to_visual(x, y)
        return (vx * scale, (self.height - vy) * scale)

    def screen_to_user(self, px: float, py: float, scale: float) -> tuple[float, float]:
        return self.visual_to_user(px / scale, self.height - py / scale)

    def user_rect_to_screen(self, rect: Rect, scale: float) -> tuple[float, float, float, float]:
        """Retângulo do espaço do usuário em tela, como (x, y, largura, altura) — o formato
        do QRectF, com (x, y) no canto superior esquerdo."""
        vleft, vbottom, vright, vtop = self.user_rect_to_visual(rect)
        return (
            vleft * scale,
            (self.height - vtop) * scale,
            (vright - vleft) * scale,
            (vtop - vbottom) * scale,
        )

    def visual_rect_to_pixels(self, rect: Rect, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        """Converte um retângulo visual para pixels de um bitmap da página inteira.

        Devolve (x0, y0, x1, y1) com origem no topo e x1/y1 exclusivos, arredondando para
        fora: o retângulo em pixels sempre cobre toda a área pedida (nunca menos), que é o
        lado seguro para redação.
        """
        scale_x = image_width / self.width
        scale_y = image_height / self.height
        vleft, vbottom, vright, vtop = rect
        x0 = _floor(vleft * scale_x)
        x1 = _ceil(vright * scale_x)
        y0 = _floor((self.height - vtop) * scale_y)
        y1 = _ceil((self.height - vbottom) * scale_y)
        return (
            max(0, min(image_width, x0)),
            max(0, min(image_height, y0)),
            max(0, min(image_width, x1)),
            max(0, min(image_height, y1)),
        )


# Tolerância para erro de ponto flutuante (ex.: 99.99999999 não deve virar um pixel a mais).
def _floor(value: float) -> int:
    return math.floor(value + 1e-6)


def _ceil(value: float) -> int:
    return math.ceil(value - 1e-6)
