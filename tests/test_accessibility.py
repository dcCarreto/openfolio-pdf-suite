"""Testes de core/accessibility.py: checador de acessibilidade (subconjunto de PDF/UA)."""

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

from core.accessibility import CheckAccessibility, FixBasicAccessibilityIssues
from core.base import EncryptedPDFError


def _make_plain_pdf(path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def _make_tagged_pdf(path, figures_alt: list) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    kids = ArrayObject()
    for alt in figures_alt:
        figure = DictionaryObject()
        figure[NameObject("/Type")] = NameObject("/StructElem")
        figure[NameObject("/S")] = NameObject("/Figure")
        if alt is not None:
            figure[NameObject("/Alt")] = TextStringObject(alt)
        kids.append(writer._add_object(figure))

    struct_root = DictionaryObject()
    struct_root[NameObject("/Type")] = NameObject("/StructTreeRoot")
    struct_root[NameObject("/K")] = kids
    writer.root_object[NameObject("/StructTreeRoot")] = writer._add_object(struct_root)

    mark_info = DictionaryObject()
    mark_info[NameObject("/Marked")] = BooleanObject(True)
    writer.root_object[NameObject("/MarkInfo")] = mark_info

    writer.add_metadata({"/Title": "Documento de teste"})
    writer.root_object[NameObject("/Lang")] = TextStringObject("pt-BR")
    writer.root_object[NameObject("/ViewerPreferences")] = DictionaryObject(
        {NameObject("/DisplayDocTitle"): BooleanObject(True)}
    )

    with open(path, "wb") as f:
        writer.write(f)


def test_check_accessibility_flags_missing_lang_title_and_tags(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    report = CheckAccessibility().run(str(pdf_path))

    assert not report.is_compliant
    assert any("idioma" in issue for issue in report.issues)
    assert any("título" in issue for issue in report.issues)
    assert any("estrutura" in issue for issue in report.issues)


def test_check_accessibility_flags_figures_without_alt_text(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_tagged_pdf(pdf_path, figures_alt=["uma descrição", None])

    report = CheckAccessibility().run(str(pdf_path))

    assert not report.is_compliant
    assert any("1 figura" in issue for issue in report.issues)


def test_check_accessibility_passes_fully_tagged_document(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_tagged_pdf(pdf_path, figures_alt=["uma descrição"])

    report = CheckAccessibility().run(str(pdf_path))

    assert report.is_compliant
    assert report.issues == []


def test_check_accessibility_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        CheckAccessibility().run(str(encrypted_path))


def test_fix_basic_accessibility_issues_sets_lang_and_title(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    output_path = tmp_path / "fixed.pdf"

    FixBasicAccessibilityIssues().run(str(pdf_path), str(output_path), language="pt-BR", title="Meu documento")

    reader = PdfReader(str(output_path))
    assert reader.trailer["/Root"]["/Lang"] == "pt-BR"
    assert reader.metadata.get("/Title") == "Meu documento"
    assert bool(reader.trailer["/Root"]["/ViewerPreferences"]["/DisplayDocTitle"]) is True

    report = CheckAccessibility().run(str(output_path))
    assert not any("idioma" in issue for issue in report.issues)
    assert not any("título" in issue for issue in report.issues)
    assert any("estrutura" in issue for issue in report.issues)  # ainda não tagueado, de propósito


def test_fix_basic_accessibility_issues_requires_language_and_title(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    with pytest.raises(ValueError):
        FixBasicAccessibilityIssues().run(str(pdf_path), str(tmp_path / "out.pdf"), language="", title="x")
    with pytest.raises(ValueError):
        FixBasicAccessibilityIssues().run(str(pdf_path), str(tmp_path / "out.pdf"), language="pt-BR", title="")


def test_fix_basic_accessibility_issues_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        FixBasicAccessibilityIssues().run(
            str(encrypted_path), str(tmp_path / "out.pdf"), language="pt-BR", title="x"
        )


def test_figures_inside_an_indirect_kids_array_are_checked(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_tagged_pdf(pdf_path, figures_alt=[None])
    writer = PdfWriter(clone_from=str(pdf_path))
    root = writer.root_object["/StructTreeRoot"].get_object()
    root[NameObject("/K")] = writer._add_object(ArrayObject(root["/K"]))  # /K indireto
    writer.write(str(pdf_path))

    report = CheckAccessibility().run(str(pdf_path))

    assert any("1 figura" in issue for issue in report.issues)


def test_custom_tags_mapped_to_figure_are_checked(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_tagged_pdf(pdf_path, figures_alt=[None])
    writer = PdfWriter(clone_from=str(pdf_path))
    root = writer.root_object["/StructTreeRoot"].get_object()
    root["/K"][0].get_object()[NameObject("/S")] = NameObject("/Imagem")
    root[NameObject("/RoleMap")] = DictionaryObject({NameObject("/Imagem"): NameObject("/Figure")})
    writer.write(str(pdf_path))

    report = CheckAccessibility().run(str(pdf_path))

    assert any("1 figura" in issue for issue in report.issues)


def test_tab_order_display_title_and_field_labels_are_checked_and_fixed(tmp_path):
    from core.form_fields import AddFormField

    plain = tmp_path / "plain.pdf"
    _make_tagged_pdf(plain, figures_alt=["ok"])
    writer = PdfWriter(clone_from=str(plain))
    del writer.root_object["/ViewerPreferences"]
    writer.write(str(plain))
    with_field = tmp_path / "campo.pdf"
    AddFormField().run(str(plain), str(with_field), field_name="cpf", page_number=0, x=20, y=100, field_type="text")

    report = CheckAccessibility().run(str(with_field))
    assert any("DisplayDocTitle" in issue for issue in report.issues)
    assert any("/Tabs" in issue for issue in report.issues)
    assert any("/TU" in issue and "cpf" in issue for issue in report.issues)

    fixed = tmp_path / "corrigido.pdf"
    FixBasicAccessibilityIssues().run(str(with_field), str(fixed), language="pt-BR", title="Formulário")
    remaining = CheckAccessibility().run(str(fixed)).issues
    assert not any("DisplayDocTitle" in issue or "/Tabs" in issue for issue in remaining)
    assert any("/TU" in issue for issue in remaining)  # a descrição do campo é com o autor
