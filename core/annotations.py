"""Anotações e marcação sobre PDFs: realce, sublinhado, riscado, notas, caneta e carimbo.

Realce/Sublinhado/Riscado e Nota renderizam corretamente sem aparência (/AP) explícita —
o pdfium (e a maioria dos leitores) gera uma aparência padrão a partir de /QuadPoints ou do
ícone padrão de nota. Caneta (Ink) e Carimbo (FreeText), porém, não: confirmado visualmente
nesta sessão que o pdfium não desenha nada sem um /AP, então ambos ganham uma appearance
stream (Form XObject) construída à mão.
"""

from dataclasses import dataclass, field

from pypdf import PdfWriter
from pypdf.annotations import FreeText, Highlight, PolyLine, Text
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from .base import PDFOperation, open_reader, require_valid_page_index

_NOTE_SIZE = 24
_STAMP_SIZE = (160, 40)
_INK_STROKE_WIDTH = 2.5
_STAMP_FONT_SIZE = 14


@dataclass
class AnnotationSpec:
    """Descreve uma anotação pendente antes de ser gravada no PDF."""

    page_index: int
    kind: str  # "highlight" | "underline" | "strikeout" | "note" | "ink" | "stamp"
    color: str = "ffeb3b"
    quads: list[tuple[float, float, float, float]] = field(default_factory=list)
    points: list[tuple[float, float]] = field(default_factory=list)
    position: tuple[float, float] | None = None
    text: str = ""


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _quad_points(quads: list[tuple[float, float, float, float]]) -> ArrayObject:
    values: list[float] = []
    for left, bottom, right, top in quads:
        values.extend([left, top, right, top, left, bottom, right, bottom])
    return ArrayObject([FloatObject(v) for v in values])


def _bounding_rect(quads: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    lefts = [q[0] for q in quads]
    bottoms = [q[1] for q in quads]
    rights = [q[2] for q in quads]
    tops = [q[3] for q in quads]
    return (min(lefts), min(bottoms), max(rights), max(tops))


def _points_bounding_rect(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    pad = _INK_STROKE_WIDTH
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def spec_rect(spec: AnnotationSpec) -> tuple[float, float, float, float]:
    """Retângulo (left, bottom, right, top) ocupado por uma anotação pendente.

    Usado tanto para montar /Rect ao gravar quanto pelo visualizador para testar cliques
    da ferramenta "Selecionar/Apagar" contra as anotações ainda não salvas.
    """
    if spec.kind in ("highlight", "underline", "strikeout"):
        return _bounding_rect(spec.quads)
    if spec.kind == "ink":
        return _points_bounding_rect(spec.points)
    if spec.kind == "note":
        x, y = spec.position
        return (x, y, x + _NOTE_SIZE, y + _NOTE_SIZE)
    if spec.kind == "stamp":
        x, y = spec.position
        width, height = _STAMP_SIZE
        return (x, y, x + width, y + height)
    raise ValueError(f"Tipo de anotação desconhecido: {spec.kind}")


def _make_appearance_stream(writer: PdfWriter, rect, content: str, needs_font: bool = False):
    """Registra uma appearance stream (Form XObject) no writer e retorna sua referência."""
    stream = DecodedStreamObject()
    # A appearance stream usa uma fonte base14 (WinAnsi/Latin-1); caracteres fora
    # desse repertório (emoji, CJK, etc.) não seriam desenhados de qualquer forma,
    # então são substituídos em vez de derrubar a gravação da anotação inteira.
    stream.set_data(content.encode("latin-1", errors="replace"))

    resources = DictionaryObject()
    if needs_font:
        resources[NameObject("/Font")] = DictionaryObject(
            {
                NameObject("/Helv"): DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
                    }
                )
            }
        )

    left, bottom, right, top = rect
    stream.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/FormType"): NumberObject(1),
            NameObject("/BBox"): ArrayObject(
                [FloatObject(left), FloatObject(bottom), FloatObject(right), FloatObject(top)]
            ),
            NameObject("/Resources"): resources,
        }
    )
    return writer._add_object(stream)


def _ink_appearance_content(points: list[tuple[float, float]], color: str) -> str:
    r, g, b = _hex_to_rgb01(color)
    lines = [f"{_INK_STROKE_WIDTH:.2f} w", "1 J", "1 j", f"{r:.3f} {g:.3f} {b:.3f} RG"]
    x0, y0 = points[0]
    lines.append(f"{x0:.2f} {y0:.2f} m")
    for x, y in points[1:]:
        lines.append(f"{x:.2f} {y:.2f} l")
    lines.append("S")
    return "\n".join(lines) + "\n"


def _stamp_appearance_content(rect: tuple[float, float, float, float], text: str, color: str) -> str:
    left, bottom, right, top = rect
    r, g, b = _hex_to_rgb01(color)
    width, height = right - left, top - bottom
    lines = [
        "1 1 1 rg",
        f"{left:.2f} {bottom:.2f} {width:.2f} {height:.2f} re",
        "f",
        f"{r:.3f} {g:.3f} {b:.3f} RG",
        "2 w",
        f"{left + 1:.2f} {bottom + 1:.2f} {width - 2:.2f} {height - 2:.2f} re",
        "S",
        "BT",
        f"/Helv {_STAMP_FONT_SIZE} Tf",
        f"{r:.3f} {g:.3f} {b:.3f} rg",
        f"{left + 8:.2f} {bottom + height / 2 - _STAMP_FONT_SIZE / 3:.2f} Td",
        f"({_escape_pdf_text(text)}) Tj",
        "ET",
    ]
    return "\n".join(lines) + "\n"


def _text_markup_annotation(subtype: str, spec: AnnotationSpec) -> DictionaryObject:
    # Underline/StrikeOut não têm classe de conveniência no pypdf. Highlight já monta a
    # estrutura correta (/Rect, /QuadPoints, /C sobre uma MarkupAnnotation); só trocamos o
    # /Subtype depois de construído em vez de duplicar essa montagem.
    annotation = Highlight(
        rect=_bounding_rect(spec.quads),
        quad_points=_quad_points(spec.quads),
        highlight_color=spec.color,
    )
    annotation[NameObject("/Subtype")] = NameObject(f"/{subtype}")
    return annotation


def _build_annotation(writer: PdfWriter, spec: AnnotationSpec):
    if spec.kind == "highlight":
        return Highlight(
            rect=_bounding_rect(spec.quads),
            quad_points=_quad_points(spec.quads),
            highlight_color=spec.color,
        )
    if spec.kind == "underline":
        return _text_markup_annotation("Underline", spec)
    if spec.kind == "strikeout":
        return _text_markup_annotation("StrikeOut", spec)
    if spec.kind == "note":
        return Text(rect=spec_rect(spec), text=spec.text)
    if spec.kind == "ink":
        rect = spec_rect(spec)
        annotation = PolyLine(vertices=spec.points)
        appearance_ref = _make_appearance_stream(
            writer, rect, _ink_appearance_content(spec.points, spec.color)
        )
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): appearance_ref})
        return annotation
    if spec.kind == "stamp":
        rect = spec_rect(spec)
        annotation = FreeText(
            text=spec.text,
            rect=rect,
            font="Helvetica-Bold",
            bold=True,
            font_size=f"{_STAMP_FONT_SIZE}pt",
            font_color=spec.color,
            border_color=spec.color,
            background_color="ffffff",
        )
        appearance_ref = _make_appearance_stream(
            writer, rect, _stamp_appearance_content(rect, spec.text, spec.color), needs_font=True
        )
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): appearance_ref})
        return annotation
    raise ValueError(f"Tipo de anotação desconhecido: {spec.kind}")


class AddAnnotations(PDFOperation):
    """Grava uma lista de anotações pendentes em um PDF."""

    def run(self, input_path: str, output_path: str, specs: list[AnnotationSpec]) -> None:
        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        total_pages = len(reader.pages)
        for spec in specs:
            require_valid_page_index(total_pages, spec.page_index)

        writer = PdfWriter(clone_from=input_path)
        for spec in specs:
            writer.add_annotation(page_number=spec.page_index, annotation=_build_annotation(writer, spec))
        with open(output_path, "wb") as f:
            writer.write(f)
