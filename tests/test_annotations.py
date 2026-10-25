"""Testes de core/annotations.py: gravação de anotações reais em um PDF."""

import re

import pytest
from reportlab.pdfgen import canvas as rl_canvas
from pypdf import PdfReader

from core.annotations import (
    AddAnnotations,
    AnnotationSpec,
    ExportAnnotationsCSV,
    ListAnnotations,
    RemoveAnnotations,
    UpdateAnnotation,
    spec_rect,
)
from core.base import EncryptedPDFError


def _make_pdf(path, text: str) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 400))
    canvas.setFont("Helvetica", 16)
    canvas.drawString(40, 340, text)
    canvas.showPage()
    canvas.save()


def _annotations_by_subtype(path) -> dict:
    reader = PdfReader(str(path))
    result = {}
    for annotation in reader.pages[0].annotations or []:
        obj = annotation.get_object()
        result[obj["/Subtype"]] = obj
    return result


def test_highlight_underline_strikeout_write_correct_subtypes(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    specs = [
        AnnotationSpec(page_index=0, kind="highlight", color="ffeb3b", quads=[(40, 330, 100, 350)]),
        AnnotationSpec(page_index=0, kind="underline", color="2196f3", quads=[(40, 300, 100, 320)]),
        AnnotationSpec(page_index=0, kind="strikeout", color="f44336", quads=[(40, 270, 100, 290)]),
    ]
    AddAnnotations().run(str(path_in), str(path_out), specs)

    by_subtype = _annotations_by_subtype(path_out)
    assert set(by_subtype) == {"/Highlight", "/Underline", "/StrikeOut"}
    assert by_subtype["/Highlight"]["/QuadPoints"] is not None


def test_note_writes_text_annotation_with_contents(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    spec = AnnotationSpec(page_index=0, kind="note", color="ffeb3b", position=(300, 300), text="Olá!")
    AddAnnotations().run(str(path_in), str(path_out), [spec])

    by_subtype = _annotations_by_subtype(path_out)
    assert by_subtype["/Text"]["/Contents"] == "Olá!"


def test_ink_and_stamp_get_an_appearance_stream(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    specs = [
        AnnotationSpec(page_index=0, kind="ink", color="000000", points=[(10, 10), (20, 30), (40, 15)]),
        AnnotationSpec(page_index=0, kind="stamp", color="f44336", position=(100, 100), text="APROVADO"),
    ]
    AddAnnotations().run(str(path_in), str(path_out), specs)

    by_subtype = _annotations_by_subtype(path_out)
    for subtype in ("/Ink", "/FreeText"):
        annotation = by_subtype[subtype]
        assert "/AP" in annotation
        appearance = annotation["/AP"]["/N"].get_object()
        assert appearance["/Subtype"] == "/Form"
        assert len(appearance.get_data()) > 0


def test_spec_rect_matches_kind_geometry():
    highlight = AnnotationSpec(page_index=0, kind="highlight", quads=[(0, 0, 10, 20), (5, 20, 15, 30)])
    assert spec_rect(highlight) == (0, 0, 15, 30)

    note = AnnotationSpec(page_index=0, kind="note", position=(5, 5), text="x")
    left, bottom, right, top = spec_rect(note)
    assert (left, bottom) == (5, 5)
    assert right > left and top > bottom


def test_stamp_with_non_latin1_text_does_not_crash(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    spec = AnnotationSpec(
        page_index=0, kind="stamp", color="f44336", position=(100, 100), text="日本語 🎉"
    )
    AddAnnotations().run(str(path_in), str(path_out), [spec])

    by_subtype = _annotations_by_subtype(path_out)
    appearance = by_subtype["/FreeText"]["/AP"]["/N"].get_object()
    assert len(appearance.get_data()) > 0


def test_add_annotations_preserves_page_count(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    AddAnnotations().run(
        str(path_in),
        str(path_out),
        [AnnotationSpec(page_index=0, kind="highlight", quads=[(40, 330, 100, 350)])],
    )

    assert len(PdfReader(str(path_out)).pages) == len(PdfReader(str(path_in)).pages)


def test_add_annotations_rejects_out_of_range_page_index(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf(path_in, "texto de exemplo")

    with pytest.raises(ValueError):
        AddAnnotations().run(
            str(path_in),
            str(path_out),
            [AnnotationSpec(page_index=5, kind="highlight", quads=[(40, 330, 100, 350)])],
        )


def test_add_annotations_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(400, 400)])
    path_out = tmp_path / "doc_out.pdf"

    with pytest.raises(EncryptedPDFError):
        AddAnnotations().run(
            str(encrypted_path),
            str(path_out),
            [AnnotationSpec(page_index=0, kind="highlight", quads=[(40, 330, 100, 350)])],
        )


def test_export_annotations_csv(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_annotated = tmp_path / "annotated.pdf"
    _make_pdf(path_in, "texto de exemplo")

    AddAnnotations().run(
        str(path_in),
        str(path_annotated),
        [
            AnnotationSpec(page_index=0, kind="highlight", color="ffeb3b", quads=[(40, 330, 100, 350)]),
            AnnotationSpec(page_index=0, kind="note", position=(40, 200), text="Revisar este trecho"),
        ],
    )

    csv_path = tmp_path / "comentarios.csv"
    count = ExportAnnotationsCSV().run(str(path_annotated), str(csv_path))

    assert count == 2
    content = csv_path.read_text(encoding="utf-8")
    assert "Highlight" in content
    assert "Revisar este trecho" in content
    assert "ffeb3b" in content


def test_export_annotations_csv_excludes_links(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in, "texto de exemplo")
    path_with_link = tmp_path / "with_link.pdf"

    from core.links import AddLink

    AddLink().run(
        str(path_in), str(path_with_link), page_number=0, left=10, bottom=10, right=50, top=30,
        url="https://example.com",
    )

    csv_path = tmp_path / "comentarios.csv"
    count = ExportAnnotationsCSV().run(str(path_with_link), str(csv_path))

    assert count == 0


def test_export_annotations_csv_returns_zero_without_annotations(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in, "texto de exemplo")

    csv_path = tmp_path / "comentarios.csv"
    count = ExportAnnotationsCSV().run(str(path_in), str(csv_path))

    assert count == 0


def test_export_annotations_csv_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(400, 400)])

    with pytest.raises(EncryptedPDFError):
        ExportAnnotationsCSV().run(str(encrypted_path), str(tmp_path / "out.csv"))


def test_stamp_on_rotated_page_occupies_a_box_upright_on_screen():
    # Na tela, o carimbo cresce para a direita e para cima a partir do clique, com o
    # tamanho de sempre — em qualquer /Rotate.
    from core.geometry import PageGeometry

    for rotation in (0, 90, 180, 270):
        geometry = PageGeometry.from_boxes((0, 0, 612, 792), rotation=rotation)
        anchor_visual = (100.0, 200.0)
        anchor_user = geometry.visual_to_user(*anchor_visual)
        spec = AnnotationSpec(page_index=0, kind="stamp", position=anchor_user, text="OK", rotation=rotation)
        left, bottom, right, top = geometry.user_rect_to_visual(spec_rect(spec))
        assert (round(left), round(bottom)) == anchor_visual
        assert (round(right - left), round(top - bottom)) == (160, 40)


def test_dragged_stamp_grows_from_the_click_without_distorting():
    # Arrastado para qualquer lado da tela, a caixa sai do clique para aquele lado e mantém
    # a proporção 160x40: o lado mais puxado manda.
    from core.annotations import stamp_box
    from core.geometry import PageGeometry

    for rotation in (0, 90, 180, 270):
        geometry = PageGeometry.from_boxes((0, 0, 612, 792), rotation=rotation)
        start = (300.0, 300.0)
        for (dx, dy), box in (
            ((320, 10), (300, 300, 620, 380)),  # para a direita: o dobro do tamanho
            ((-40, 20), (220, 300, 300, 320)),  # para a esquerda e para cima: a altura manda
            ((-80, -80), (-20, 220, 300, 300)),
        ):
            end = geometry.visual_to_user(start[0] + dx, start[1] + dy)
            position, scale = stamp_box(geometry.visual_to_user(*start), end, rotation)
            spec = AnnotationSpec(page_index=0, kind="stamp", position=position, text="OK", rotation=rotation, scale=scale)
            assert tuple(round(v) for v in geometry.user_rect_to_visual(spec_rect(spec))) == box, (rotation, dx, dy)


def test_bigger_stamp_is_saved_with_bigger_box_and_letters(tmp_path):
    path_in, path_out = tmp_path / "doc.pdf", tmp_path / "out.pdf"
    _make_pdf(path_in, "texto")
    spec = AnnotationSpec(page_index=0, kind="stamp", position=(50, 50), text="APROVADO", scale=2)

    AddAnnotations().run(str(path_in), str(path_out), [spec])

    annotation = _annotations_by_subtype(path_out)["/FreeText"]
    assert [float(v) for v in annotation["/Rect"]] == [50, 50, 370, 130]
    assert [float(v) for v in annotation["/AP"]["/N"].get_object()["/BBox"]] == [0, 0, 320, 80]
    assert b" 28 Tf" in annotation["/AP"]["/N"].get_object().get_data()  # a letra dobrou junto


def test_stamp_appearance_is_rotated_with_the_page(tmp_path, make_text_pdf):
    path_in = make_text_pdf("rot.pdf", [(80, 650, "texto")], rotate=90)
    path_out = tmp_path / "out.pdf"
    spec = AnnotationSpec(page_index=0, kind="stamp", position=(300, 300), text="APROVADO", rotation=90)

    AddAnnotations().run(str(path_in), str(path_out), [spec])

    annotation = _annotations_by_subtype(path_out)["/FreeText"]
    appearance = annotation["/AP"]["/N"].get_object()
    assert [float(v) for v in appearance["/Matrix"]] == [0, 1, -1, 0, 0, 0]
    assert [float(v) for v in appearance["/BBox"]] == [0, 0, 160, 40]


def test_comments_csv_counts_pages_from_one_and_opens_in_excel(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_annotated = tmp_path / "annotated.pdf"
    _make_pdf(path_in, "texto de exemplo")
    AddAnnotations().run(
        str(path_in),
        str(path_annotated),
        [AnnotationSpec(page_index=0, kind="note", position=(40, 200), text="=CMD|' /C calc'!A0")],
    )
    csv_path = tmp_path / "comentarios.csv"

    ExportAnnotationsCSV().run(str(path_annotated), str(csv_path))

    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: o Excel em português lê os acentos
    rows = raw.decode("utf-8-sig").splitlines()
    assert rows[1].startswith("1,")  # primeira página = 1
    assert ",'=CMD" in rows[1]  # não vira fórmula no Excel


def test_comments_export_to_xlsx(tmp_path):
    from openpyxl import load_workbook

    path_in = tmp_path / "doc.pdf"
    path_annotated = tmp_path / "annotated.pdf"
    _make_pdf(path_in, "texto de exemplo")
    AddAnnotations().run(
        str(path_in), str(path_annotated), [AnnotationSpec(page_index=0, kind="note", position=(40, 200), text="Ótimo")]
    )
    xlsx_path = tmp_path / "comentarios.xlsx"

    ExportAnnotationsCSV().run(str(path_annotated), str(xlsx_path))

    rows = list(load_workbook(xlsx_path).active.iter_rows(values_only=True))
    assert rows[0] == ("pagina", "tipo", "autor", "texto", "cor")
    assert rows[1][0] == 1 and rows[1][3] == "Ótimo"


def test_ink_is_saved_as_ink_with_color_width_author_and_date(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "out.pdf"
    _make_pdf(path_in, "texto")

    AddAnnotations().run(
        str(path_in),
        str(path_out),
        [AnnotationSpec(page_index=0, kind="ink", color="ff0000", points=[(10, 10), (20, 30), (40, 15)])],
        author="Revisora",
    )

    (ink,) = [ref.get_object() for ref in PdfReader(str(path_out)).pages[0]["/Annots"]]
    assert ink["/Subtype"] == "/Ink"
    assert [float(v) for v in ink["/InkList"][0]] == [10, 10, 20, 30, 40, 15]
    assert [float(v) for v in ink["/C"]] == [1, 0, 0]
    assert float(ink["/BS"]["/W"]) > 0
    assert ink["/T"] == "Revisora"
    assert str(ink["/M"]).startswith("D:")


def test_note_keeps_the_chosen_color(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "out.pdf"
    _make_pdf(path_in, "texto")

    AddAnnotations().run(
        str(path_in), str(path_out), [AnnotationSpec(page_index=0, kind="note", color="2196f3", position=(40, 200), text="oi")]
    )

    (note,) = [ref.get_object() for ref in PdfReader(str(path_out)).pages[0]["/Annots"]]
    assert [round(float(v), 2) for v in note["/C"]] == [0.13, 0.59, 0.95]
    assert note["/T"]  # autor padrão: o usuário do sistema


def test_stamp_appearance_uses_the_embedded_font_and_fits_long_text(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "out.pdf"
    _make_pdf(path_in, "texto")

    AddAnnotations().run(
        str(path_in),
        str(path_out),
        [AnnotationSpec(page_index=0, kind="stamp", position=(100, 100), text="ŁÓDŹ ΩМЕГА — APROVADO COM RESSALVAS")],
    )

    appearance = _annotations_by_subtype(path_out)["/FreeText"]["/AP"]["/N"].get_object()
    fonts = [ref.get_object() for ref in appearance["/Resources"]["/Font"].values()]
    (font,) = [f for f in fonts if "DejaVuSans-Bold" in str(f["/BaseFont"])]
    descendant = font["/DescendantFonts"][0].get_object() if "/DescendantFonts" in font else font
    assert "/FontFile2" in descendant["/FontDescriptor"]  # embutida
    sizes = [float(token) for token in re.findall(rb"([\d.]+) Tf", appearance.get_data())]
    assert sizes and min(sizes) < 14  # texto longo encolhe para caber na caixa


def _annotated_with_reply_and_link(tmp_path):
    """Nota com popup e resposta, um realce e um link, nessa ordem em /Annots."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    def annotation(subtype, **extra):
        result = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject(subtype),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (10, 10, 40, 40)]),
            }
        )
        for key, value in extra.items():
            result[NameObject(f"/{key}")] = TextStringObject(value) if isinstance(value, str) else value
        return result

    writer = PdfWriter()
    writer.add_blank_page(400, 400)
    note = writer.add_annotation(0, annotation("/Text", Contents="Original", T="Ana", RC="<body>Original</body>"))
    writer.add_annotation(0, annotation("/Popup", Parent=note.indirect_reference))
    writer.add_annotation(0, annotation("/Text", Contents="Resposta", IRT=note.indirect_reference))
    writer.add_annotation(0, annotation("/Highlight", Contents="Realce"))
    writer.add_annotation(0, annotation("/Link"))
    path = tmp_path / "comentado.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_list_annotations_gives_position_rect_and_date(tmp_path):
    path = _annotated_with_reply_and_link(tmp_path)

    comments = ListAnnotations().run(str(path))

    assert [(c.kind, c.index, c.content) for c in comments] == [
        ("Text", 0, "Original"),
        ("Text", 2, "Resposta"),
        ("Highlight", 3, "Realce"),
    ]
    assert comments[0].rect == (10, 10, 40, 40) and comments[0].author == "Ana"


def test_update_annotation_changes_text_author_and_drops_rich_text(tmp_path):
    path, out = _annotated_with_reply_and_link(tmp_path), tmp_path / "editado.pdf"

    UpdateAnnotation().run(str(path), str(out), 0, 0, "Texto novo", "Bia")

    note = PdfReader(str(out)).pages[0]["/Annots"][0].get_object()
    assert note["/Contents"] == "Texto novo" and note["/T"] == "Bia"
    assert "/RC" not in note and str(note["/M"]).startswith("D:")


def test_remove_annotation_takes_its_popup_and_replies(tmp_path):
    path, out = _annotated_with_reply_and_link(tmp_path), tmp_path / "removido.pdf"

    assert RemoveAnnotations().run(str(path), str(out), [(0, 0)]) == 3

    subtypes = [a.get_object()["/Subtype"] for a in PdfReader(str(out)).pages[0]["/Annots"]]
    assert subtypes == ["/Highlight", "/Link"]


def test_editing_a_comment_that_is_not_there_fails_without_writing(tmp_path):
    path, out = _annotated_with_reply_and_link(tmp_path), tmp_path / "x.pdf"

    with pytest.raises(ValueError, match="não existe mais"):
        RemoveAnnotations().run(str(path), str(out), [(0, 4)])  # o link não é comentário
    with pytest.raises(ValueError, match="não existe mais"):
        UpdateAnnotation().run(str(path), str(out), 0, 9, "x", "")
    assert not out.exists()


def test_new_annotations_get_a_unique_name(tmp_path):
    path_in, path_out = tmp_path / "doc.pdf", tmp_path / "out.pdf"
    _make_pdf(path_in, "texto")
    specs = [AnnotationSpec(page_index=0, kind="note", position=(10, 10), text=str(n)) for n in range(2)]
    AddAnnotations().run(str(path_in), str(path_out), specs)

    names = [a.get_object()["/NM"] for a in PdfReader(str(path_out)).pages[0]["/Annots"]]
    assert len(set(names)) == 2



def _render(path):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    image = document[0].render(scale=1, draw_annots=True).to_pil().convert("RGB")
    document.close()
    return image


def _count(image, box, color) -> int:
    """Pixels de `color` (com folga) dentro de `box` (left, top, right, bottom na imagem)."""
    left, top, right, bottom = box
    return sum(
        1
        for x in range(left, right)
        for y in range(top, bottom)
        if all(abs(a - b) < 60 for a, b in zip(image.getpixel((x, y)), color))
    )


def test_shapes_get_their_subtype_width_and_appearance(tmp_path):
    path_in, path_out = tmp_path / "doc.pdf", tmp_path / "formas.pdf"
    _make_pdf(path_in, "")
    specs = [
        AnnotationSpec(page_index=0, kind="square", color="ff0000", points=[(50, 50), (150, 120)], width=4),
        AnnotationSpec(page_index=0, kind="circle", color="0000ff", points=[(200, 50), (300, 150)], width=3),
        AnnotationSpec(page_index=0, kind="arrow", color="00aa00", points=[(60, 250), (300, 250)], width=2),
    ]

    AddAnnotations().run(str(path_in), str(path_out), specs)

    found = _annotations_by_subtype(path_out)
    assert set(found) == {"/Square", "/Circle", "/Line"}
    assert [float(v) for v in found["/Square"]["/Rect"]] == [50, 50, 150, 120]
    assert float(found["/Square"]["/BS"]["/W"]) == 4
    assert [float(v) for v in found["/Line"]["/L"]] == [60, 250, 300, 250]
    assert list(found["/Line"]["/LE"]) == ["/None", "/OpenArrow"]
    image = _render(path_out)  # 400 x 400, y de cima para baixo
    assert _count(image, (48, 278, 152, 284), (255, 0, 0)) > 100  # a borda de baixo do retângulo
    assert _count(image, (95, 290, 105, 340), (255, 0, 0)) == 0  # vazado: o meio não é pintado
    assert _count(image, (245, 247, 255, 256), (0, 0, 255)) > 10  # o topo do círculo
    assert _count(image, (280, 135, 300, 165), (0, 170, 0)) > 20  # a ponta da seta


def test_pen_width_is_used_for_ink(tmp_path):
    path_in, path_out = tmp_path / "doc.pdf", tmp_path / "caneta.pdf"
    _make_pdf(path_in, "")
    spec = AnnotationSpec(page_index=0, kind="ink", color="000000", points=[(50, 200), (300, 200)], width=8)

    AddAnnotations().run(str(path_in), str(path_out), [spec])

    ink = _annotations_by_subtype(path_out)["/Ink"]
    assert float(ink["/BS"]["/W"]) == 8
    assert spec_rect(spec) == (42, 192, 308, 208)
    assert _count(_render(path_out), (150, 195, 152, 206), (0, 0, 0)) >= 14  # 8 pt de traço, não 2,5


def test_author_is_written_on_new_annotations(tmp_path):
    path_in, path_out = tmp_path / "doc.pdf", tmp_path / "out.pdf"
    _make_pdf(path_in, "Texto")

    AddAnnotations().run(str(path_in), str(path_out), [AnnotationSpec(0, "note", position=(50, 50))], author="Ana Revisora")

    assert _annotations_by_subtype(path_out)["/Text"]["/T"] == "Ana Revisora"


def test_moving_a_highlight_moves_its_quad_points(tmp_path):
    from core.annotations import MoveAnnotation

    path_in, marked, moved = tmp_path / "doc.pdf", tmp_path / "marcado.pdf", tmp_path / "movido.pdf"
    _make_pdf(path_in, "Texto")
    AddAnnotations().run(str(path_in), str(marked), [AnnotationSpec(0, "highlight", quads=[(40, 330, 140, 350)])])
    (info,) = ListAnnotations().run(str(marked))

    MoveAnnotation().run(str(marked), str(moved), 0, info.index, (100, 100, 300, 140))

    highlight = _annotations_by_subtype(moved)["/Highlight"]
    assert [float(v) for v in highlight["/Rect"]] == [100, 100, 300, 140]
    assert [float(v) for v in highlight["/QuadPoints"]] == [100, 140, 300, 140, 100, 100, 300, 100]


def test_moving_ink_moves_the_drawing(tmp_path):
    from core.annotations import MoveAnnotation

    path_in, marked, moved = tmp_path / "doc.pdf", tmp_path / "marcado.pdf", tmp_path / "movido.pdf"
    _make_pdf(path_in, "")
    AddAnnotations().run(
        str(path_in), str(marked), [AnnotationSpec(0, "ink", color="000000", points=[(50, 350), (150, 350)], width=6)]
    )
    (info,) = ListAnnotations().run(str(marked))
    left, bottom, right, top = info.rect

    MoveAnnotation().run(str(marked), str(moved), 0, info.index, (left, bottom - 250, right, top - 250))

    ink = _annotations_by_subtype(moved)["/Ink"]
    assert [round(float(v)) for v in ink["/InkList"][0]] == [50, 100, 150, 100]
    image = _render(moved)
    assert _count(image, (95, 45, 105, 55), (0, 0, 0)) == 0  # saiu de y 350 (50 px do topo)
    assert _count(image, (95, 295, 105, 305), (0, 0, 0)) > 20  # e foi para y 100


def test_recolor_redraws_or_drops_the_appearance(tmp_path):
    from core.annotations import RecolorAnnotations

    path_in, marked, recolored = tmp_path / "doc.pdf", tmp_path / "marcado.pdf", tmp_path / "cor.pdf"
    _make_pdf(path_in, "Texto")
    AddAnnotations().run(
        str(path_in),
        str(marked),
        [
            AnnotationSpec(0, "highlight", quads=[(40, 330, 140, 350)]),
            AnnotationSpec(0, "square", color="ff0000", points=[(50, 50), (150, 120)], width=4),
            AnnotationSpec(0, "stamp", position=(200, 200), text="OK"),
        ],
    )
    items = [(info.page_index, info.index) for info in ListAnnotations().run(str(marked))]

    assert RecolorAnnotations().run(str(marked), str(recolored), items, "0000ff") == (2, 1)  # o carimbo fica

    found = _annotations_by_subtype(recolored)
    assert [round(float(v), 2) for v in found["/Highlight"]["/C"]] == [0, 0, 1] and "/AP" not in found["/Highlight"]
    assert [round(float(v), 2) for v in found["/Square"]["/C"]] == [0, 0, 1]
    image = _render(recolored)
    assert _count(image, (48, 278, 152, 284), (0, 0, 255)) > 100  # o retângulo foi redesenhado em azul
    assert _count(image, (48, 278, 152, 284), (255, 0, 0)) == 0
