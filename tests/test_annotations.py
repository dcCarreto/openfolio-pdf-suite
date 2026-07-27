"""Testes de core/annotations.py: gravação de anotações reais em um PDF."""

import pytest
from reportlab.pdfgen import canvas as rl_canvas
from pypdf import PdfReader

from core.annotations import AddAnnotations, AnnotationSpec, spec_rect
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
    for subtype in ("/PolyLine", "/FreeText"):
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
