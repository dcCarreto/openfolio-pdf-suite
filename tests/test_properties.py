"""Testes de core/properties.py: o que o painel de propriedades mostra."""

import pytest
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError, forget_password, remember_password
from core.fonts import SANS, register_fonts
from core.properties import ReadDocumentProperties


def _make_pdf(path) -> None:
    """Página A4 com Helvetica (padrão, não embutida) e a fonte do app (embutida, subconjunto),
    uma página Carta deitada pela /Rotate e um formulário com a mesma Helvetica."""
    register_fonts()
    canvas = rl_canvas.Canvas(str(path), pagesize=(595.28, 841.89))
    canvas.setTitle("Relatório")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(40, 800, "texto padrao")
    canvas.setFont(SANS, 12)
    canvas.drawString(40, 780, "texto embutido")
    canvas.showPage()
    canvas.setPageSize((612, 792))
    canvas.setFont("Helvetica", 12)
    canvas.drawString(40, 700, "carta")
    canvas.showPage()
    canvas.save()
    writer = PdfWriter(clone_from=str(path))
    writer.pages[1].rotate(90)
    with open(path, "wb") as f:
        writer.write(f)


def test_fonts_say_whether_they_are_embedded_and_where_they_are_used(tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)

    properties = ReadDocumentProperties().run(str(path))

    by_name = {font.name: font for font in properties.fonts}
    helvetica = by_name["Helvetica"]
    assert not helvetica.embedded and helvetica.standard and helvetica.pages == [0, 1]
    embedded = next(font for name, font in by_name.items() if name != "Helvetica")
    assert embedded.embedded and embedded.subset and not embedded.standard
    assert embedded.kind.startswith("TrueType") and embedded.pages == [0]


def test_general_information_and_page_sizes(tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)

    properties = ReadDocumentProperties().run(str(path))

    assert properties.version.startswith("1.")
    assert properties.page_count == 2
    assert properties.file_size == path.stat().st_size
    assert properties.metadata["title"] == "Relatório"
    assert properties.metadata["producer"]
    assert not properties.encryption and properties.permissions is None
    assert not properties.tagged and not properties.pdfa and properties.form_fields == 0
    sizes = [(group.width, group.height, group.pages) for group in properties.page_sizes]
    assert sizes == [(595.3, 841.9, [0]), (792.0, 612.0, [1])]  # a Carta aparece deitada


def test_protection_method_and_permissions(make_pdf, tmp_path):
    plain = make_pdf("plain.pdf", [(200, 200)])
    restricted = tmp_path / "restrito.pdf"
    writer = PdfWriter(clone_from=str(plain))
    writer.encrypt(
        user_password="",
        owner_password="dono",
        algorithm="AES-128",
        permissions_flag=UserAccessPermissions.PRINT | UserAccessPermissions.FILL_FORM_FIELDS,
    )
    with open(restricted, "wb") as f:
        writer.write(f)

    properties = ReadDocumentProperties().run(str(restricted))

    assert properties.encryption == "AES-128" and not properties.needs_password
    assert properties.permissions["print"] and properties.permissions["fill_forms"]
    assert not properties.permissions["copy"] and not properties.permissions["modify"]


def test_password_protected_document_needs_the_password(make_encrypted_pdf):
    path = make_encrypted_pdf("senha.pdf", [(200, 200)])
    with pytest.raises(EncryptedPDFError):
        ReadDocumentProperties().run(str(path))

    remember_password(path, "segredo123")
    try:
        properties = ReadDocumentProperties().run(str(path))
    finally:
        forget_password(path)
    assert properties.encryption == "AES-256" and properties.needs_password
    assert all(properties.permissions.values())


def test_newer_catalog_version_wins_over_the_header(make_pdf, tmp_path):
    from pypdf.generic import NameObject

    path = tmp_path / "v.pdf"
    writer = PdfWriter(clone_from=str(make_pdf("p.pdf", [(100, 100)])))
    writer._root_object[NameObject("/Version")] = NameObject("/2.0")
    with open(path, "wb") as f:
        writer.write(f)

    assert ReadDocumentProperties().run(str(path)).version == "2.0"


def test_fonts_inside_annotation_appearances_count(tmp_path):
    from core.annotations import AddAnnotations, AnnotationSpec

    path, stamped = tmp_path / "doc.pdf", tmp_path / "carimbo.pdf"
    _make_pdf(path)
    AddAnnotations().run(str(path), str(stamped), [AnnotationSpec(page_index=1, kind="stamp", position=(50, 50), text="OK")])

    fonts = ReadDocumentProperties().run(str(stamped)).fonts
    assert any(font.name.endswith("Bold") and font.pages == [1] for font in fonts)


def test_subsets_of_one_font_and_near_equal_page_sizes_are_one_line(tmp_path):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for width, prefix in ((595.0, "ABCDEF"), (595.6, "GHIJKL")):
        page = writer.add_blank_page(width, 842)
        font_file = writer._add_object(DecodedStreamObject())
        descriptor = DictionaryObject({NameObject("/FontFile2"): font_file})
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/TrueType"),
                NameObject("/BaseFont"): NameObject(f"/{prefix}+Contrato"),
                NameObject("/FontDescriptor"): writer._add_object(descriptor),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf (x) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
    path = tmp_path / "montado.pdf"
    with open(path, "wb") as f:
        writer.write(f)

    properties = ReadDocumentProperties().run(str(path))

    assert [(f.name, f.pages) for f in properties.fonts] == [("Contrato", [0, 1])]
    assert [g.pages for g in properties.page_sizes] == [[0, 1]]
