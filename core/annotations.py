"""Anotações e marcação sobre PDFs: realce, sublinhado, riscado, notas, caneta e carimbo.

Realce/Sublinhado/Riscado e Nota renderizam corretamente sem aparência (/AP) explícita —
o pdfium (e a maioria dos leitores) gera uma aparência padrão a partir de /QuadPoints ou do
ícone padrão de nota. Caneta (Ink) e Carimbo (FreeText), porém, não: confirmado visualmente
nesta sessão que o pdfium não desenha nada sem um /AP, então ambos ganham uma appearance
stream (Form XObject) construída à mão.
"""

import datetime
import getpass
import io
import uuid
from dataclasses import dataclass, field

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText, Highlight, Text
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from reportlab.pdfgen import canvas as rl_canvas

from .base import READ, PDFOperation, add_object, open_reader, require_valid_page_index, write_pdf
from .fonts import SANS_BOLD, register_fonts, text_width
from .geometry import normalize_rect
from .messages import Message
from .tabular import write_table

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
    # /Rotate da página: nota e carimbo crescem para a direita e para cima *na tela* a
    # partir de `position`, e o texto do carimbo fica de pé também em páginas giradas.
    rotation: int = 0


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    red, green, blue = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return red, green, blue


def _color_array(hex_color: str) -> ArrayObject:
    return ArrayObject([FloatObject(round(v, 4)) for v in _hex_to_rgb01(hex_color)])


def _pdf_date(moment: datetime.datetime) -> str:
    offset = moment.utcoffset() or datetime.timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return moment.strftime("D:%Y%m%d%H%M%S") + f"{sign}{minutes // 60:02d}'{minutes % 60:02d}'"


def default_author() -> str:
    """O nome de usuário do sistema, como o Acrobat usa por padrão no autor dos comentários."""
    try:
        return getpass.getuser()
    except Exception:
        return ""


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


# Direção, no espaço do usuário, dos eixos x e y da tela para cada /Rotate.
_VISUAL_AXES = {
    0: ((1, 0), (0, 1)),
    90: ((0, 1), (-1, 0)),
    180: ((-1, 0), (0, -1)),
    270: ((0, -1), (1, 0)),
}


def _visual_box(x: float, y: float, width: float, height: float, rotation: int) -> tuple[float, float, float, float]:
    """Retângulo do espaço do usuário ocupado por uma caixa `width` x `height` que, na tela,
    começa em (x, y) e cresce para a direita e para cima."""
    (ux, uy), (vx, vy) = _VISUAL_AXES.get(rotation % 360, _VISUAL_AXES[0])
    corners = [(x + a * ux + b * vx, y + a * uy + b * vy) for a in (0, width) for b in (0, height)]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return (min(xs), min(ys), max(xs), max(ys))


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
        assert spec.position is not None
        x, y = spec.position
        return _visual_box(x, y, _NOTE_SIZE, _NOTE_SIZE, spec.rotation)
    if spec.kind == "stamp":
        assert spec.position is not None
        x, y = spec.position
        width, height = _STAMP_SIZE
        return _visual_box(x, y, width, height, spec.rotation)
    raise ValueError(f"Tipo de anotação desconhecido: {spec.kind}")


def _make_appearance_stream(writer: PdfWriter, rect, content: bytes | str, resources=None, matrix=None):
    """Registra uma appearance stream (Form XObject) no writer e retorna sua referência.
    `rect` vira a /BBox; `matrix`, se informada, é a /Matrix do formulário."""
    stream = DecodedStreamObject()
    stream.set_data(content if isinstance(content, bytes) else content.encode("latin-1"))
    resources = resources if resources is not None else DictionaryObject()

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
    if matrix is not None:
        stream[NameObject("/Matrix")] = ArrayObject([FloatObject(v) for v in matrix])
    return add_object(writer, stream)


def _ink_appearance_content(
    strokes: list[list[tuple[float, float]]], color: str, width: float = _INK_STROKE_WIDTH, closed: bool = False
) -> str:
    """Traços (caneta, linha, polígono) da aparência; `closed` fecha cada traço."""
    r, g, b = _hex_to_rgb01(color)
    lines = [f"{width:.2f} w", "1 J", "1 j", f"{r:.3f} {g:.3f} {b:.3f} RG"]
    for points in strokes:
        x0, y0 = points[0]
        lines.append(f"{x0:.2f} {y0:.2f} m")
        for x, y in points[1:]:
            lines.append(f"{x:.2f} {y:.2f} l")
        lines.append("s" if closed else "S")
    return "\n".join(lines) + "\n"


def _stamp_appearance(writer: PdfWriter, width: float, height: float, text: str, color: str):
    """Conteúdo e recursos da aparência do carimbo, desenhados pelo reportlab com a fonte
    embutida (`core/fonts.py`): antes a aparência usava a Helvetica base14, e acentos fora
    do Latin-1, grego ou cirílico viravam "?". Um texto longo encolhe para caber na caixa."""
    register_fonts()
    r, g, b = _hex_to_rgb01(color)
    available = width - 16
    size: float = _STAMP_FONT_SIZE
    natural = text_width(text, SANS_BOLD, size)
    if natural > available > 0:
        size = max(6.0, size * available / natural)

    def draw(canvas):
        canvas.setFillColorRGB(1, 1, 1)
        canvas.rect(0, 0, width, height, stroke=0, fill=1)
        canvas.setStrokeColorRGB(r, g, b)
        canvas.setLineWidth(2)
        canvas.rect(1, 1, width - 2, height - 2, stroke=1, fill=0)
        canvas.setFillColorRGB(r, g, b)
        canvas.setFont(SANS_BOLD, size)
        canvas.drawString(8, height / 2 - size / 3, text)

    return canvas_appearance(writer, width, height, draw)


def canvas_appearance(writer: PdfWriter, width: float, height: float, draw):
    """Conteúdo e recursos de uma aparência `width` x `height` desenhada pelo reportlab
    com `draw(canvas)`, prontos para `_make_appearance_stream`."""
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(width, height))
    draw(canvas)
    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    page = PdfReader(buffer).pages[0]
    contents = page.get_contents()
    assert contents is not None  # o reportlab sempre grava o conteúdo
    return contents.get_data(), page["/Resources"].clone(writer)


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
        note = Text(rect=spec_rect(spec), text=spec.text)
        note[NameObject("/C")] = _color_array(spec.color)  # antes a cor escolhida era ignorada
        return note
    if spec.kind == "ink":
        # Caneta é /Ink com /InkList (antes era gravada como /PolyLine, sem cor nem
        # espessura: leitores que regeneram a aparência mostravam outro traço).
        rect = spec_rect(spec)
        annotation = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Ink"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
                NameObject("/InkList"): ArrayObject(
                    [ArrayObject([FloatObject(v) for point in spec.points for v in point])]
                ),
                NameObject("/C"): _color_array(spec.color),
                NameObject("/BS"): DictionaryObject(
                    {NameObject("/W"): FloatObject(_INK_STROKE_WIDTH), NameObject("/S"): NameObject("/S")}
                ),
            }
        )
        appearance_ref = _make_appearance_stream(
            writer, rect, _ink_appearance_content([spec.points], spec.color)
        )
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): appearance_ref})
        return annotation
    if spec.kind == "stamp":
        rect = spec_rect(spec)
        width, height = _STAMP_SIZE
        rotation = spec.rotation % 360
        (ux, uy), (vx, vy) = _VISUAL_AXES.get(rotation, _VISUAL_AXES[0])
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
        # A aparência é desenhada "de pé" num quadro local (0, 0, largura, altura); a
        # /Matrix gira esse quadro junto com os eixos da tela, e o leitor o encaixa no /Rect.
        content, resources = _stamp_appearance(writer, width, height, spec.text, spec.color)
        appearance_ref = _make_appearance_stream(
            writer,
            (0, 0, width, height),
            content,
            resources=resources,
            matrix=(ux, uy, vx, vy, 0, 0),
        )
        if rotation:
            annotation[NameObject("/Rotate")] = NumberObject(rotation)
        # A borda de 2 pt da aparência; sem /BS, quem refaz a aparência (ou o XFDF) usa 1 pt.
        annotation[NameObject("/BS")] = DictionaryObject(
            {NameObject("/W"): FloatObject(2), NameObject("/S"): NameObject("/S")}
        )
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): appearance_ref})
        return annotation
    raise ValueError(f"Tipo de anotação desconhecido: {spec.kind}")


class AddAnnotations(PDFOperation):
    """Grava uma lista de anotações pendentes em um PDF. Cada uma recebe autor (`/T`; por
    padrão o usuário do sistema) e data (`/M`), que os leitores mostram na lista de
    comentários."""

    def run(self, input_path: str, output_path: str, specs: list[AnnotationSpec], author: str | None = None) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for spec in specs:
            require_valid_page_index(total_pages, spec.page_index)

        author = default_author() if author is None else author
        now = _pdf_date(datetime.datetime.now().astimezone())
        writer = PdfWriter(clone_from=reader)
        for spec in specs:
            annotation = _build_annotation(writer, spec)
            if author:
                annotation[NameObject("/T")] = TextStringObject(author)
            annotation[NameObject("/M")] = TextStringObject(now)
            annotation[NameObject("/CreationDate")] = TextStringObject(now)
            # Nome único: o XFDF identifica a anotação por ele (reimportar atualiza, não duplica).
            annotation[NameObject("/NM")] = TextStringObject(str(uuid.uuid4()))
            writer.add_annotation(page_number=spec.page_index, annotation=annotation)
        write_pdf(writer, output_path)


@dataclass
class AnnotationInfo:
    """Descrição resumida de uma anotação/comentário já existente num PDF."""

    page_index: int
    kind: str
    author: str
    content: str
    color: str
    index: int = 0  # posição em /Annots da página: identifica a anotação para editar/remover
    rect: tuple[float, float, float, float] | None = None
    date: str = ""  # /M, como está no PDF ("D:20261019143000-03'00'")


_NON_COMMENT_SUBTYPES = {"/Link", "/Widget", "/Popup"}


def comment_annotations(page):
    """(posição em /Annots, anotação) de cada comentário da página: links, widgets de
    formulário e popups ficam de fora (não são comentários de revisão)."""
    for index, annotation_ref in enumerate(page.get("/Annots", None) or []):
        annotation = annotation_ref.get_object()
        if str(annotation.get("/Subtype", "")) not in _NON_COMMENT_SUBTYPES:
            yield index, annotation


def _object_key(value):
    """Identidade de um objeto do PDF, seja a referência indireta ou o próprio objeto."""
    if hasattr(value, "idnum"):
        return (value.idnum, value.generation)
    reference = getattr(value, "indirect_reference", None)
    return (reference.idnum, reference.generation) if reference is not None else id(value)


def remove_page_annotations(page, indexes: set[int]) -> int:
    """Tira de /Annots as anotações nessas posições, com o popup delas e as respostas (/IRT)
    a elas, como o Acrobat faz ao apagar um comentário. Devolve quantas saíram."""
    annots = page.get("/Annots", None)
    if not annots or not indexes:
        return 0
    annots = annots.get_object()
    removed = {_object_key(annots[i]) for i in indexes}
    changed = True
    while changed:  # respostas a respostas
        changed = False
        for entry in annots:
            key = _object_key(entry)
            annotation = entry.get_object()
            linked = annotation.get("/IRT") if "/IRT" in annotation else annotation.get("/Parent")
            if key not in removed and linked is not None and _object_key(linked) in removed:
                removed.add(key)
                changed = True
    kept = [entry for entry in annots if _object_key(entry) not in removed]
    page[NameObject("/Annots")] = ArrayObject(kept)
    return len(annots) - len(kept)


def _comment_at(writer: PdfWriter, page_index: int, index: int):
    require_valid_page_index(len(writer.pages), page_index)
    for position, annotation in comment_annotations(writer.pages[page_index]):
        if position == index:
            return annotation
    raise ValueError(Message("A anotação escolhida não existe mais no documento."))


class ListAnnotations(PDFOperation):
    """Os comentários já existentes no PDF, página a página, na ordem de /Annots."""

    def run(self, input_path: str) -> list[AnnotationInfo]:
        reader = open_reader(input_path, purpose=READ)
        result = []
        for page_index, page in enumerate(reader.pages):
            for index, annotation in comment_annotations(page):
                rect = annotation.get("/Rect")
                result.append(
                    AnnotationInfo(
                        page_index=page_index,
                        kind=str(annotation.get("/Subtype", "")).lstrip("/"),
                        author=str(annotation.get("/T", "") or ""),
                        content=str(annotation.get("/Contents", "") or ""),
                        color=_describe_annotation_color(annotation.get("/C")),
                        index=index,
                        rect=normalize_rect(rect) if rect and len(rect) == 4 else None,
                        date=str(annotation.get("/M", "") or ""),
                    )
                )
        return result


class UpdateAnnotation(PDFOperation):
    """Troca o texto e o autor de um comentário existente e atualiza a data de alteração.
    O texto formatado (/RC) sai junto: o Acrobat o mostra no lugar de /Contents, e ele
    continuaria com o texto antigo."""

    def run(self, input_path: str, output_path: str, page_index: int, index: int, content: str, author: str) -> None:
        writer = PdfWriter(clone_from=open_reader(input_path))
        annotation = _comment_at(writer, page_index, index)
        annotation[NameObject("/Contents")] = TextStringObject(content)
        if author:
            annotation[NameObject("/T")] = TextStringObject(author)
        else:
            annotation.pop("/T", None)
        annotation.pop("/RC", None)
        annotation[NameObject("/M")] = TextStringObject(_pdf_date(datetime.datetime.now().astimezone()))
        write_pdf(writer, output_path)


class RemoveAnnotations(PDFOperation):
    """Remove comentários existentes, dados como (página, posição em /Annots), com os
    popups e as respostas deles. Devolve quantas anotações saíram."""

    def run(self, input_path: str, output_path: str, items: list[tuple[int, int]]) -> int:
        writer = PdfWriter(clone_from=open_reader(input_path))
        by_page: dict[int, set[int]] = {}
        for page_index, index in items:
            _comment_at(writer, page_index, index)
            by_page.setdefault(page_index, set()).add(index)
        removed = sum(remove_page_annotations(writer.pages[p], indexes) for p, indexes in by_page.items())
        write_pdf(writer, output_path)
        return removed


def _describe_annotation_color(color_array) -> str:
    if not color_array:
        return ""
    values = [float(v) for v in color_array]
    if len(values) == 1:
        gray = round(values[0] * 255)
        return f"{gray:02x}{gray:02x}{gray:02x}"
    if len(values) == 3:
        return "".join(f"{round(v * 255):02x}" for v in values)
    if len(values) == 4:
        return ",".join(f"{v:.2f}" for v in values)  # CMYK: sem conversão exata para hex RGB
    return ""


class ExportAnnotationsCSV(PDFOperation):
    """Exporta os comentários/anotações já existentes num PDF para CSV (ou Excel, se o
    arquivo terminar em .xlsx — ver `core/tabular.py`): página (a partir de 1), tipo, autor,
    texto e cor. Ignora links, widgets de formulário e popups de anotação (não são
    "comentários" no sentido de revisão de documento)."""

    def run(self, input_path: str, output_path: str) -> int:
        rows = ListAnnotations().run(input_path)
        write_table(
            output_path,
            ["pagina", "tipo", "autor", "texto", "cor"],
            ([row.page_index + 1, row.kind, row.author, row.content, row.color] for row in rows),
        )

        return len(rows)
