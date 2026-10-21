"""Exporta e importa comentários em XFDF (ISO 19444-1), o XML que o Acrobat e outros
leitores usam para trocar comentários de revisão sem mandar o PDF inteiro.

Vão e voltam nota, realce, sublinhado, riscado, ondulado, caneta, texto livre, carimbo,
retângulo, círculo, linha, polígono e polilinha, com autor, data, texto, cor, nome e
resposta (`inreplyto`). O `<appearance>` do Acrobat não é lido nem gravado: ao importar,
a aparência é refeita aqui para os tipos que o pdfium não desenha sozinho (caneta, linha,
polígono, polilinha, texto livre e carimbo); realce, nota, retângulo e círculo o leitor
desenha a partir da geometria.
"""

import os
import re
import uuid
from typing import cast
from xml.etree import ElementTree

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from .annotations import (
    _VISUAL_AXES,
    _describe_annotation_color,
    _hex_to_rgb01,
    _ink_appearance_content,
    _make_appearance_stream,
    _object_key,
    _stamp_appearance,
    canvas_appearance,
    comment_annotations,
    remove_page_annotations,
)
from .base import READ, PDFOperation, atomic_output, open_reader, replace_object, write_pdf
from .fonts import SANS, SANS_BOLD, register_fonts, wrap_text
from .messages import Message

_NAMESPACE = "http://ns.adobe.com/xfdf/"

_ELEMENTS = {
    "/Text": "text",
    "/Highlight": "highlight",
    "/Underline": "underline",
    "/StrikeOut": "strikeout",
    "/Squiggly": "squiggly",
    "/Ink": "ink",
    "/FreeText": "freetext",
    "/Stamp": "stamp",
    "/Square": "square",
    "/Circle": "circle",
    "/Line": "line",
    "/Polygon": "polygon",
    "/PolyLine": "polyline",
}
_SUBTYPES = {element: subtype for subtype, element in _ELEMENTS.items()}

# Bits de /F na ordem da especificação (bit 1 = invisible).
_FLAGS = ["invisible", "hidden", "print", "nozoom", "norotate", "noview", "readonly", "locked", "togglenoview", "lockedcontents"]

_TEXT_ATTRIBUTES = [("/T", "title"), ("/Subj", "subject"), ("/M", "date"), ("/CreationDate", "creationdate"), ("/NM", "name")]


def _number(value) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _numbers(values) -> str:
    return ",".join(_number(v) for v in values)


def _points(values) -> str:
    """"x,y;x,y;..." — o formato de `<gesture>` e `<vertices>`."""
    values = [float(v) for v in values]
    return ";".join(f"{_number(x)},{_number(y)}" for x, y in zip(values[::2], values[1::2]))


def _hex(color_array) -> str | None:
    value = _describe_annotation_color(color_array)
    return f"#{value.upper()}" if len(value) == 6 and "," not in value else None


def _clean(value) -> str:
    """Texto do PDF sem os caracteres de controle que o XML não aceita."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


# -- exportar -------------------------------------------------------------------------


def _element(page_index: int, annotation, names: dict) -> ElementTree.Element:
    subtype = str(annotation["/Subtype"])
    attrs = {"page": str(page_index)}
    if "/Rect" in annotation:
        attrs["rect"] = _numbers(annotation["/Rect"])
    for key, attr in _TEXT_ATTRIBUTES:
        if annotation.get(key):
            attrs[attr] = _clean(annotation[key])
    for key, attr in (("/C", "color"), ("/IC", "interior-color")):
        color = _hex(annotation.get(key))
        if color:
            attrs[attr] = color
    flags = int(annotation.get("/F", 0) or 0)
    if flags:
        attrs["flags"] = ",".join(name for bit, name in enumerate(_FLAGS) if flags & (1 << bit))
    if "/CA" in annotation:
        attrs["opacity"] = _number(annotation["/CA"])
    if annotation.get("/Rotate"):
        attrs["rotation"] = str(int(annotation["/Rotate"]))
    border = annotation.get("/BS")
    if border is not None and "/W" in border.get_object():
        attrs["width"] = _number(border.get_object()["/W"])
    if "/Name" in annotation:
        attrs["icon"] = str(annotation["/Name"]).lstrip("/")
    if "/QuadPoints" in annotation:
        attrs["coords"] = _numbers(annotation["/QuadPoints"])
    if subtype == "/Line" and len(annotation.get("/L", [])) == 4:
        line = [float(v) for v in annotation["/L"]]
        attrs["start"], attrs["end"] = _numbers(line[:2]), _numbers(line[2:])
    if "/IRT" in annotation and _object_key(annotation["/IRT"]) in names:
        attrs["inreplyto"] = names[_object_key(annotation["/IRT"])]

    element = ElementTree.Element(_ELEMENTS[subtype], attrs)
    if annotation.get("/Contents"):
        ElementTree.SubElement(element, "contents").text = _clean(annotation["/Contents"])
    if subtype == "/FreeText":
        for key, tag in (("/DA", "defaultappearance"), ("/DS", "defaultstyle")):
            if annotation.get(key):
                ElementTree.SubElement(element, tag).text = _clean(annotation[key])
    if subtype == "/Ink":
        inklist = ElementTree.SubElement(element, "inklist")
        for gesture in annotation.get("/InkList", []):
            ElementTree.SubElement(inklist, "gesture").text = _points(gesture)
    if subtype in ("/Polygon", "/PolyLine") and "/Vertices" in annotation:
        ElementTree.SubElement(element, "vertices").text = _points(annotation["/Vertices"])
    return element


class ExportAnnotationsXFDF(PDFOperation):
    """Grava os comentários do PDF num arquivo XFDF. Devolve (exportados, ignorados): os
    ignorados são comentários de outros tipos (anexo, som, legenda...)."""

    def run(self, input_path: str, output_path: str) -> tuple[int, int]:
        reader = open_reader(input_path, purpose=READ)
        comments = [(p, a) for p, page in enumerate(reader.pages) for _i, a in comment_annotations(page)]
        names = {_object_key(a): _clean(a["/NM"]) for _p, a in comments if a.get("/NM")}

        root = ElementTree.Element("xfdf", {"xmlns": _NAMESPACE, "xml:space": "preserve"})
        annots = ElementTree.SubElement(root, "annots")
        skipped = 0
        for page_index, annotation in comments:
            if str(annotation.get("/Subtype", "")) in _ELEMENTS:
                annots.append(_element(page_index, annotation, names))
            else:
                skipped += 1
        ElementTree.SubElement(root, "f", {"href": os.path.basename(input_path)})
        ids = reader.trailer.get("/ID")
        if ids and len(ids) == 2:
            original, modified = (bytes(getattr(v.get_object(), "original_bytes", v.get_object())).hex().upper() for v in ids)
            ElementTree.SubElement(root, "ids", {"original": original, "modified": modified})

        ElementTree.indent(root)
        with atomic_output(output_path) as temp_path:
            ElementTree.ElementTree(root).write(temp_path, encoding="UTF-8", xml_declaration=True)
        return len(annots), skipped


# -- importar -------------------------------------------------------------------------


def _floats(text: str | None, count: int | None = None) -> list[float]:
    values = [float(v) for v in re.split(r"[\s,;]+", (text or "").strip()) if v]
    if not values or (count is not None and len(values) != count) or len(values) % 2:
        raise ValueError
    return values


def _float_array(values) -> ArrayObject:
    return ArrayObject([FloatObject(v) for v in values])


def _color(text: str | None) -> tuple[float, float, float] | None:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", (text or "").strip())
    return _hex_to_rgb01(match.group(1)) if match else None


def _child(element, name: str):
    return next((child for child in element if _local(child.tag) == name), None)


def _child_text(element, name: str) -> str | None:
    child = _child(element, name)
    return "".join(child.itertext()) if child is not None else None


def _free_text_appearance(writer, width: float, height: float, annotation) -> tuple:
    """Fundo (/C), borda (/BS, cor do /DA) e texto quebrado em linhas na fonte embutida,
    com cor, tamanho e negrito do /DS ou do /DA."""
    style = str(annotation.get("/DS", ""))
    appearance = str(annotation.get("/DA", ""))
    rgb = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", appearance)
    da_color = tuple(float(v) for v in rgb.groups()) if rgb else (0.0, 0.0, 0.0)
    style_color = re.search(r"color\s*:\s*#([0-9a-fA-F]{6})", style)
    text_color = _hex_to_rgb01(style_color.group(1)) if style_color else da_color
    size_match = re.search(r"([\d.]+)\s*pt", style) or re.search(r"([\d.]+)\s+Tf", appearance)
    size = float(size_match.group(1)) if size_match else 12.0
    size = size if size > 0 else 12.0
    font = SANS_BOLD if "bold" in style else SANS
    border = annotation.get("/BS")
    border_width = float(border["/W"]) if border is not None and "/W" in border else 1.0
    background = [float(v) for v in annotation.get("/C", [])]
    text = str(annotation.get("/Contents", "") or "")
    register_fonts()

    def draw(canvas):
        if len(background) == 3:
            canvas.setFillColorRGB(*background)
            canvas.rect(0, 0, width, height, stroke=0, fill=1)
        if border_width > 0:
            canvas.setStrokeColorRGB(*da_color)
            canvas.setLineWidth(border_width)
            canvas.rect(border_width / 2, border_width / 2, width - border_width, height - border_width, stroke=1, fill=0)
        canvas.setFillColorRGB(*text_color)
        canvas.setFont(font, size)
        margin = border_width + 2
        y = height - margin - size
        for paragraph in text.splitlines():
            for line in wrap_text(paragraph, font, size, width - 2 * margin) or [""]:
                if y < 0:
                    return
                canvas.drawString(margin, y, line)
                y -= size * 1.2

    return canvas_appearance(writer, width, height, draw)


def _build(writer: PdfWriter, subtype: str, element) -> DictionaryObject:
    rect = _floats(element.get("rect"), 4)
    left, bottom, right, top = min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/Rect"): _float_array((left, bottom, right, top)),
        }
    )
    for key, attr in _TEXT_ATTRIBUTES:
        if element.get(attr):
            annotation[NameObject(key)] = TextStringObject(element.get(attr))
    for key, attr in (("/C", "color"), ("/IC", "interior-color")):
        color = _color(element.get(attr))
        if color:
            annotation[NameObject(key)] = _float_array(round(v, 4) for v in color)
    flags = {name.strip().lower() for name in (element.get("flags") or "").split(",")}
    bits = sum(1 << bit for bit, name in enumerate(_FLAGS) if name in flags)
    if bits:
        annotation[NameObject("/F")] = NumberObject(bits)
    if element.get("opacity"):
        annotation[NameObject("/CA")] = FloatObject(min(1.0, max(0.0, float(element.get("opacity")))))
    rotation = int(float(element.get("rotation") or 0)) % 360
    if rotation % 90:
        rotation = 0
    if rotation:
        annotation[NameObject("/Rotate")] = NumberObject(rotation)
    width = float(element.get("width")) if element.get("width") else None
    if width is not None:
        annotation[NameObject("/BS")] = DictionaryObject(
            {NameObject("/W"): FloatObject(width), NameObject("/S"): NameObject("/S")}
        )
    if element.get("icon"):
        annotation[NameObject("/Name")] = NameObject("/" + re.sub(r"[^A-Za-z0-9_.-]", "", element.get("icon")))
    contents = _child_text(element, "contents")
    if contents is None:
        contents = _child_text(element, "contents-richtext")
    if contents:
        annotation[NameObject("/Contents")] = TextStringObject(contents)

    color_hex = "".join(f"{round(v * 255):02x}" for v in _color(element.get("color")) or (0, 0, 0))
    stroke_width = width if width is not None else 1.0
    strokes, closed = [], False
    if subtype in ("/Highlight", "/Underline", "/StrikeOut", "/Squiggly"):
        coords = _floats(element.get("coords"))
        if len(coords) % 8:
            raise ValueError
        annotation[NameObject("/QuadPoints")] = _float_array(coords)
    elif subtype == "/Ink":
        inklist = _child(element, "inklist")
        gestures = [_floats(g.text) for g in inklist if _local(g.tag) == "gesture"] if inklist is not None else []
        if not gestures:
            raise ValueError
        annotation[NameObject("/InkList")] = ArrayObject([_float_array(g) for g in gestures])
        strokes = [list(zip(g[::2], g[1::2])) for g in gestures]
    elif subtype == "/Line":
        line = _floats(element.get("start"), 2) + _floats(element.get("end"), 2)
        annotation[NameObject("/L")] = _float_array(line)
        strokes = [[(line[0], line[1]), (line[2], line[3])]]
    elif subtype in ("/Polygon", "/PolyLine"):
        vertices = _floats(_child_text(element, "vertices"))
        annotation[NameObject("/Vertices")] = _float_array(vertices)
        strokes, closed = [list(zip(vertices[::2], vertices[1::2]))], subtype == "/Polygon"
    elif subtype == "/FreeText":
        for key, tag in (("/DA", "defaultappearance"), ("/DS", "defaultstyle")):
            value = _child_text(element, tag)
            if value:
                annotation[NameObject(key)] = TextStringObject(value)

    if strokes:
        content = _ink_appearance_content(strokes, color_hex, stroke_width, closed=closed)
        reference = _make_appearance_stream(writer, (left, bottom, right, top), content)
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): reference})
    elif subtype in ("/FreeText", "/Stamp"):
        # Desenhada de pé num quadro local; a /Matrix gira o quadro com a página (como o
        # carimbo de `AddAnnotations`).
        box_width, box_height = right - left, top - bottom
        if rotation in (90, 270):
            box_width, box_height = box_height, box_width
        if subtype == "/FreeText":
            content, resources = _free_text_appearance(writer, box_width, box_height, annotation)
        else:
            label = contents or str(annotation.get("/Name", "/Stamp")).lstrip("/")
            content, resources = _stamp_appearance(writer, box_width, box_height, label, color_hex)
        (ux, uy), (vx, vy) = _VISUAL_AXES[rotation]
        reference = _make_appearance_stream(
            writer, (0, 0, box_width, box_height), content, resources=resources, matrix=(ux, uy, vx, vy, 0, 0)
        )
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): reference})
    return annotation


def _read_xfdf(xfdf_path: str):
    with open(xfdf_path, "rb") as file:
        data = file.read()
    # O XFDF não usa DTD; recusar DOCTYPE fecha a porta a entidades (expansão e externas).
    if b"<!DOCTYPE" in data.upper():
        raise ValueError(Message("O arquivo XFDF tem uma declaração DOCTYPE, que não é aceita."))
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        raise ValueError(Message("O arquivo escolhido não é um XFDF válido.")) from None
    if _local(root.tag) != "xfdf":
        raise ValueError(Message("O arquivo escolhido não é um XFDF válido."))
    annots = _child(root, "annots")
    return list(annots) if annots is not None else []


class ImportAnnotationsXFDF(PDFOperation):
    """Acrescenta ao PDF os comentários de um arquivo XFDF. Um comentário com o mesmo nome
    (`name`/`/NM`) de outro que já está no documento o substitui, então importar de novo
    o XFDF atualizado de um revisor não duplica nada. Devolve (importados, ignorados): os
    ignorados são de tipos não suportados, de páginas que não existem ou malformados."""

    def run(self, input_path: str, xfdf_path: str, output_path: str) -> tuple[int, int]:
        elements = _read_xfdf(xfdf_path)
        writer = PdfWriter(clone_from=open_reader(input_path))
        total_pages = len(writer.pages)
        existing = {
            str(annotation["/NM"]): page_index
            for page_index, page in enumerate(writer.pages)
            for _index, annotation in comment_annotations(page)
            if annotation.get("/NM")
        }
        added: dict[str, DictionaryObject] = {}  # nome -> anotação, para ligar as respostas
        replies = []
        imported = skipped = 0

        for element in elements:
            subtype = _SUBTYPES.get(_local(element.tag))
            try:
                page_index = int(element.get("page", ""))
                if subtype is None or not 0 <= page_index < total_pages:
                    raise ValueError
                annotation = _build(writer, subtype, element)
            except (ValueError, TypeError):
                skipped += 1
                continue

            name = str(annotation.get("/NM") or uuid.uuid4())
            annotation[NameObject("/NM")] = TextStringObject(name)
            page = writer.pages[page_index]
            old = self._named(page, name) if existing.get(name) == page_index else None
            if old is not None and old.indirect_reference is not None:
                # No mesmo lugar: respostas e popup do comentário antigo continuam ligados a ele.
                for key in ("/Popup", "/P"):
                    if key in old:
                        annotation[NameObject(key)] = old.raw_get(key)
                replace_object(writer, old.indirect_reference, annotation)
                annotation = cast(DictionaryObject, writer.get_object(old.indirect_reference))
            else:
                if name in existing:
                    other = writer.pages[existing[name]]
                    remove_page_annotations(other, {i for i, a in comment_annotations(other) if a.get("/NM") == name})
                annotation = writer.add_annotation(page_index, annotation)
            existing[name] = page_index
            added[name] = annotation
            if element.get("inreplyto"):
                replies.append((annotation, element.get("inreplyto"), page_index))
            imported += 1

        for annotation, parent_name, page_index in replies:
            parent = added.get(parent_name) or self._named(writer.pages[page_index], parent_name)
            if parent is not None and parent.indirect_reference is not None:
                annotation[NameObject("/IRT")] = parent.indirect_reference

        write_pdf(writer, output_path)
        return imported, skipped

    @staticmethod
    def _named(page, name: str):
        return next((a for _i, a in comment_annotations(page) if str(a.get("/NM", "")) == name), None)
