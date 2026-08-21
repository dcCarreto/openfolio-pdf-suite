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
