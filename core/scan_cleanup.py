"""Limpeza de documentos escaneados (A08): remove páginas em branco, endireita páginas
tortas e corta as margens brancas.

Cada página é renderizada em tons de cinza a 100 DPI e vira uma máscara de "tinta" (pixels
escuros, sem os pontinhos isolados de poeira e sem a borda de 1% onde o scanner costuma
deixar sombra). Com ela:

- página em branco: quase nenhuma tinta;
- inclinação: o ângulo (até 5° para cada lado) em que as linhas de texto ficam mais
  "horizontais", isto é, em que a soma de cada linha de pixels varia mais de uma linha para
  a outra; a página é endireitada girando o conteúdo em torno do centro (`cm`), sem
  re-renderizar nada, então o texto de um OCR anterior gira junto;
- margens: a menor área com toda a tinta (depois de endireitar), com folga, vira a nova
  CropBox/MediaBox, como na aba Cortar.
"""

import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject

from .base import PDFOperation, open_pdfium, open_reader, write_pdf
from .crop import _clip_other_boxes
from .document import pages_writer
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes
from .progress import PDFIUM_LOCK, Progress, ensure_progress

_SCALE = 100 / 72
_INK_LEVEL = 160  # cinza abaixo disso é tinta
_BORDER = 0.01  # fração de cada lado ignorada (sombra da borda do scanner)
_BLANK_FRACTION = 0.0003  # menos tinta que isso (~1 palavra curta numa A4): página em branco
_MAX_SKEW = 5.0
_MIN_SKEW = 0.2  # abaixo disso, girar só borraria a página à toa
_MARGIN = 12.0  # folga, em pontos, em volta do conteúdo ao cortar


@dataclass
class ScanCleanupResult:
    """Páginas (índices do documento de entrada) afetadas por cada limpeza."""

    removed: list[int] = field(default_factory=list)
    straightened: list[int] = field(default_factory=list)
    cropped: list[int] = field(default_factory=list)


class CleanScannedPages(PDFOperation):
    def run(
        self,
        input_path: str,
        output_path: str,
        remove_blank: bool = True,
        deskew: bool = True,
        crop_margins: bool = True,
        progress: Progress | None = None,
    ) -> ScanCleanupResult:
        if not (remove_blank or deskew or crop_margins):
            raise ValueError("Escolha pelo menos uma limpeza.")
        progress = ensure_progress(progress)
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)
        result = ScanCleanupResult()
        total = len(reader.pages)

        with PDFIUM_LOCK:
            pdfium_doc = open_pdfium(input_path)
        try:
            for index in range(total):
                progress.update(index, total, "Analisando as páginas")
                with PDFIUM_LOCK:
                    pdfium_page = pdfium_doc[index]
                    geometry = PageGeometry.from_pdfium_page(pdfium_page)
                    gray = pdfium_page.render(scale=_SCALE).to_pil().convert("L")
                    pdfium_page.close()
                mask = ink_mask(gray)
                ink = mask.histogram()[255]
                if ink <= _BLANK_FRACTION * mask.width * mask.height:
                    if remove_blank:
                        result.removed.append(index)
                    continue

                page = writer.pages[index]
                angle = skew_angle(mask) if deskew else 0.0
                if angle:
                    left, bottom, right, top = geometry.box
                    center_x, center_y = (left + right) / 2, (bottom + top) / 2
                    # A rotação é própria (não espelha), então o sentido é o mesmo no espaço
                    # do usuário e na tela, qualquer que seja o /Rotate.
                    page.add_transformation(
                        Transformation().translate(-center_x, -center_y).rotate(angle).translate(center_x, center_y)
                    )
                    mask = mask.rotate(angle, resample=Image.Resampling.NEAREST)
                    result.straightened.append(index)

                if crop_margins:
                    box = _content_box(mask, geometry)
                    if box is not None:
                        page.mediabox = box
                        page.cropbox = box
                        _clip_other_boxes(page, box)
                        result.cropped.append(index)
        finally:
            with PDFIUM_LOCK:
                pdfium_doc.close()

        if len(result.removed) == total:
            raise ValueError("Todas as páginas parecem em branco; nada foi alterado.")
        progress.update(total, total, "Gravando")
        if result.removed:
            # Remover passando pelo pages_writer leva junto marcadores e links das páginas.
            buffer = io.BytesIO()
            writer.write(buffer)
            cleaned = PdfReader(buffer)
            kept = [index for index in range(total) if index not in set(result.removed)]
            writer = pages_writer([(cleaned, kept)])
        write_pdf(writer, output_path)
        return result


def ink_mask(gray: Image.Image) -> Image.Image:
    """Tinta = 255, papel = 0, sem pontinhos isolados nem a borda da página."""
    mask = gray.point(lambda value: 255 if value < _INK_LEVEL else 0).filter(ImageFilter.MedianFilter(3))
    border_x, border_y = max(1, round(mask.width * _BORDER)), max(1, round(mask.height * _BORDER))
    ImageDraw.Draw(mask).rectangle((0, 0, mask.width - 1, mask.height - 1), outline=0, width=max(border_x, border_y))
    return mask


def _profile_score(mask: Image.Image, angle: float) -> float:
    rotated = mask.rotate(angle, resample=Image.Resampling.NEAREST) if angle else mask
    rows = rotated.resize((1, rotated.height), Image.Resampling.BOX).tobytes()
    return float(sum((b - a) ** 2 for a, b in zip(rows, rows[1:])))


def skew_angle(mask: Image.Image) -> float:
    """Ângulo (graus, anti-horário) que endireita a página, ou 0 se ela já está reta ou se
    não há linhas de texto para medir."""
    candidates = [step / 2 for step in range(int(-_MAX_SKEW * 2), int(_MAX_SKEW * 2) + 1)]
    scores = {angle: _profile_score(mask, angle) for angle in candidates}
    coarse = max(scores, key=scores.get)
    for step in range(-4, 5):
        angle = round(coarse + step / 10, 1)
        if angle not in scores and abs(angle) <= _MAX_SKEW:
            scores[angle] = _profile_score(mask, angle)
    best = max(scores, key=scores.get)
    # Sem um ganho claro sobre a página como está (foto, desenho), melhor não mexer.
    if abs(best) < _MIN_SKEW or scores[best] <= scores[0.0] * 1.1:
        return 0.0
    return best


def _content_box(mask: Image.Image, geometry: PageGeometry) -> RectangleObject | None:
    """A área com toda a tinta mais a folga, no espaço do usuário; None se isso quase não
    muda a página."""
    bbox = mask.getbbox()
    if bbox is None:
        return None
    scale_x, scale_y = mask.width / geometry.width, mask.height / geometry.height
    x0, y0, x1, y1 = bbox
    visual = (
        max(0.0, x0 / scale_x - _MARGIN),
        max(0.0, geometry.height - y1 / scale_y - _MARGIN),
        min(geometry.width, x1 / scale_x + _MARGIN),
        min(geometry.height, geometry.height - y0 / scale_y + _MARGIN),
    )
    if (visual[2] - visual[0]) * (visual[3] - visual[1]) > 0.95 * geometry.width * geometry.height:
        return None
    return RectangleObject(geometry.visual_rect_to_user(visual))
