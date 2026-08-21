"""Testes de core/pdfa.py: conversão para PDF/A (aproximação) e verificação."""

import pytest
from pypdf import PdfReader, PdfWriter

from core.base import EncryptedPDFError
from core.pdfa import ConvertToPDFA, ValidatePDFA


def _plain_pdf(path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def _pdf_with_js_and_attachment(path) -> None:
    plain_path = str(path).replace(".pdf", "_src.pdf")
    _plain_pdf(plain_path)

    writer = PdfWriter(clone_from=plain_path)
    writer.add_js('app.alert("oi");')
    writer.add_attachment("secreto.txt", b"dados anexados")
    writer.add_annotation(
        page_number=0,
        annotation={
            "/Subtype": "/Link",
            "/Rect": [10, 10, 50, 30],
            "/A": {"/S": "/JavaScript", "/JS": 'app.alert("annotation js");'},
        },
    )
    with open(path, "wb") as f:
        writer.write(f)


def test_convert_to_pdfa_removes_javascript_and_attachments(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)
    path_out = tmp_path / "out.pdf"

    ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="b")

    reader = PdfReader(str(path_out))
    assert list(reader.attachments.keys()) == []
    annots = [ref.get_object() for ref in reader.pages[0]["/Annots"]]
    link = next(a for a in annots if a["/Subtype"] == "/Link")
    assert "/A" not in link


def test_convert_to_pdfa_writes_xmp_metadata(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)
    path_out = tmp_path / "out.pdf"

    ConvertToPDFA().run(str(path_in), str(path_out), part=1, conformance="a")

    reader = PdfReader(str(path_out))
    metadata_ref = reader.trailer["/Root"]["/Metadata"]
    xmp = metadata_ref.get_object().get_data().decode("utf-8")
    assert "<pdfaid:part>1<" in xmp
    assert "<pdfaid:conformance>A<" in xmp


def test_convert_to_pdfa_rejects_invalid_part_and_conformance(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)

    with pytest.raises(ValueError):
        ConvertToPDFA().run(str(path_in), str(tmp_path / "out.pdf"), part=9)
    with pytest.raises(ValueError):
        ConvertToPDFA().run(str(path_in), str(tmp_path / "out.pdf"), conformance="Z")


def test_convert_to_pdfa_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ConvertToPDFA().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_validate_pdfa_flags_encryption_js_and_attachments(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)

    result = ValidatePDFA().run(str(path_in))

    assert not result.is_valid
    assert any("JavaScript" in issue for issue in result.issues)
    assert any("anexos" in issue for issue in result.issues)


def test_validate_pdfa_passes_converted_document(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)
    path_out = tmp_path / "out.pdf"
    ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="b")

    result = ValidatePDFA().run(str(path_out), part=2, conformance="b")

    assert result.is_valid
    assert result.issues == []


def test_validate_pdfa_flags_missing_metadata(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)

    result = ValidatePDFA().run(str(path_in))

    assert not result.is_valid
    assert any("metadados XMP" in issue for issue in result.issues)
