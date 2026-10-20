"""Testes de core/xfdf.py: comentários indo e voltando em XFDF."""

from xml.etree import ElementTree

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from reportlab.pdfgen import canvas as rl_canvas

from core.annotations import AddAnnotations, AnnotationSpec, ListAnnotations
from core.xfdf import ExportAnnotationsXFDF, ImportAnnotationsXFDF


def _make_pdf(path, pages: int = 1) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 400))
    for number in range(pages):
        canvas.drawString(40, 340, f"pagina {number + 1}")
        canvas.showPage()
    canvas.save()


def _ink_pixels(path, rect, page_index: int = 0) -> int:
    """Pixels que não são brancos dentro de `rect` (espaço do usuário, página 400x400 a 1x)."""
    document = pdfium.PdfDocument(str(path))
    image = document[page_index].render(scale=1, draw_annots=True).to_pil().convert("L")
    left, bottom, right, top = rect
    crop = image.crop((int(left), int(400 - top), int(right), int(400 - bottom)))
    document.close()
    return sum(1 for value in crop.tobytes() if value < 200)


def _summary(path) -> list[tuple]:
    return [(a.page_index, a.kind, a.author, a.content, a.color) for a in ListAnnotations().run(str(path))]


_SPECS = [
    AnnotationSpec(page_index=0, kind="highlight", color="ffeb3b", quads=[(40, 330, 140, 350)]),
    AnnotationSpec(page_index=0, kind="note", color="2196f3", position=(300, 300), text="Revisar\nesta parte"),
    AnnotationSpec(page_index=1, kind="ink", color="f44336", points=[(50, 50), (120, 90), (160, 60)]),
    AnnotationSpec(page_index=1, kind="stamp", color="4caf50", position=(200, 200), text="APROVADO"),
]


def test_comments_go_to_xfdf_and_back_with_their_look(tmp_path):
    original, annotated = tmp_path / "doc.pdf", tmp_path / "anotado.pdf"
    xfdf, imported = tmp_path / "comentarios.xfdf", tmp_path / "importado.pdf"
    _make_pdf(original, pages=2)
    AddAnnotations().run(str(original), str(annotated), _SPECS, author="Ana Revisora")

    assert ExportAnnotationsXFDF().run(str(annotated), str(xfdf)) == (4, 0)
    assert ImportAnnotationsXFDF().run(str(original), str(xfdf), str(imported)) == (4, 0)

    assert _summary(imported) == _summary(annotated)
    assert all(row[2] == "Ana Revisora" for row in _summary(imported))
    # Caneta e carimbo só aparecem com /AP: a importação refaz a aparência.
    assert _ink_pixels(imported, (50, 50, 160, 90), 1) > 20
    assert _ink_pixels(imported, (200, 200, 360, 240), 1) > 100


def test_xfdf_is_the_adobe_format(tmp_path):
    original, annotated, xfdf = tmp_path / "doc.pdf", tmp_path / "anotado.pdf", tmp_path / "c.xfdf"
    _make_pdf(original, pages=2)
    AddAnnotations().run(str(original), str(annotated), _SPECS, author="Ana")
    ExportAnnotationsXFDF().run(str(annotated), str(xfdf))

    root = ElementTree.parse(xfdf).getroot()
    ns = "{http://ns.adobe.com/xfdf/}"
    assert root.tag == f"{ns}xfdf"
    tags = [child.tag.removeprefix(ns) for child in root.find(f"{ns}annots")]
    assert tags == ["highlight", "text", "ink", "freetext"]
    highlight = root.find(f"{ns}annots/{ns}highlight")
    assert highlight.get("page") == "0" and highlight.get("color") == "#FFEB3B"
    assert highlight.get("title") == "Ana" and highlight.get("name") and highlight.get("coords")
    assert root.find(f"{ns}annots/{ns}text/{ns}contents").text == "Revisar\nesta parte"
    assert root.find(f"{ns}annots/{ns}ink/{ns}inklist/{ns}gesture").text == "50,50;120,90;160,60"
    assert root.find(f"{ns}f").get("href") == "anotado.pdf"


def test_importing_the_same_xfdf_again_updates_instead_of_duplicating(tmp_path):
    original, annotated, xfdf = tmp_path / "doc.pdf", tmp_path / "anotado.pdf", tmp_path / "c.xfdf"
    _make_pdf(original, pages=2)
    AddAnnotations().run(str(original), str(annotated), _SPECS)
    ExportAnnotationsXFDF().run(str(annotated), str(xfdf))
    text = xfdf.read_text(encoding="utf-8").replace("Revisar\nesta parte", "Texto novo")
    xfdf.write_text(text, encoding="utf-8")

    again = tmp_path / "de_novo.pdf"
    ImportAnnotationsXFDF().run(str(annotated), str(xfdf), str(again))

    rows = _summary(again)
    assert len(rows) == 4
    assert [row[3] for row in rows if row[1] == "Text"] == ["Texto novo"]


def test_replies_keep_pointing_to_their_comment(tmp_path):
    source = tmp_path / "respostas.pdf"
    writer = PdfWriter()
    writer.add_blank_page(400, 400)

    def note(name, text):
        return DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Text"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (10, 10, 34, 34)]),
                NameObject("/NM"): TextStringObject(name),
                NameObject("/Contents"): TextStringObject(text),
            }
        )

    parent = writer.add_annotation(0, note("pai", "Comentário"))
    reply = note("filho", "Resposta")
    reply[NameObject("/IRT")] = parent.indirect_reference
    writer.add_annotation(0, reply)
    with open(source, "wb") as f:
        writer.write(f)

    xfdf, blank, imported = tmp_path / "r.xfdf", tmp_path / "branco.pdf", tmp_path / "importado.pdf"
    ExportAnnotationsXFDF().run(str(source), str(xfdf))
    assert 'inreplyto="pai"' in xfdf.read_text(encoding="utf-8")
    _make_pdf(blank)
    ImportAnnotationsXFDF().run(str(blank), str(xfdf), str(imported))

    annotations = {str(a.get_object()["/NM"]): a.get_object() for a in PdfReader(str(imported)).pages[0]["/Annots"]}
    assert annotations["filho"]["/IRT"].get_object()["/NM"] == "pai"


def test_shapes_from_another_reader_are_drawn(tmp_path):
    pdf, xfdf, imported = tmp_path / "doc.pdf", tmp_path / "formas.xfdf", tmp_path / "importado.pdf"
    _make_pdf(pdf)
    xfdf.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve"><annots>
  <line page="0" rect="40,40,160,160" color="#FF0000" width="3" start="50,50" end="150,150" title="Bia"/>
  <polygon page="0" rect="200,40,360,160" color="#0000FF" width="2"><vertices>210,50;350,50;280,150</vertices></polygon>
  <freetext page="0" rect="40,200,300,260" color="#FFFFFF" width="0">
    <contents>Texto livre importado</contents>
    <defaultappearance>0 0 0 rg /Helv 14 Tf</defaultappearance>
  </freetext>
  <caret page="0" rect="1,1,5,5"/>
  <square page="9" rect="1,1,5,5"/>
  <circle page="0" rect="quebrado"/>
</annots></xfdf>""",
        encoding="utf-8",
    )

    assert ImportAnnotationsXFDF().run(str(pdf), str(xfdf), str(imported)) == (3, 3)
    assert _ink_pixels(imported, (40, 40, 160, 160)) > 100
    assert _ink_pixels(imported, (200, 40, 360, 160)) > 100
    assert _ink_pixels(imported, (40, 200, 300, 260)) > 100


def test_xfdf_with_doctype_or_invalid_xml_is_refused(tmp_path):
    pdf, xfdf = tmp_path / "doc.pdf", tmp_path / "x.xfdf"
    _make_pdf(pdf)
    xfdf.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><xfdf/>', encoding="utf-8")
    with pytest.raises(ValueError, match="DOCTYPE"):
        ImportAnnotationsXFDF().run(str(pdf), str(xfdf), str(tmp_path / "out.pdf"))

    xfdf.write_text("<xfdf><annots>", encoding="utf-8")
    with pytest.raises(ValueError, match="XFDF válido"):
        ImportAnnotationsXFDF().run(str(pdf), str(xfdf), str(tmp_path / "out.pdf"))
    assert not (tmp_path / "out.pdf").exists()


def test_export_skips_links_and_unsupported_comments(tmp_path):
    source, xfdf = tmp_path / "doc.pdf", tmp_path / "x.xfdf"
    writer = PdfWriter()
    writer.add_blank_page(400, 400)
    for subtype in ("/Link", "/FileAttachment", "/Square"):
        writer.add_annotation(
            0,
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject(subtype),
                    NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (10, 10, 50, 50)]),
                }
            ),
        )
    with open(source, "wb") as f:
        writer.write(f)

    assert ExportAnnotationsXFDF().run(str(source), str(xfdf)) == (1, 1)
