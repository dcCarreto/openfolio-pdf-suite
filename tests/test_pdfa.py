"""Testes de core/pdfa.py: conversão para PDF/A e verificação (B27)."""

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfgen import canvas as rl_canvas

import core.pdfa as pdfa
from core.base import EncryptedPDFError
from core.fonts import SANS, register_fonts
from core.pdfa import ConvertToPDFA, ValidatePDFA


@pytest.fixture(autouse=True)
def _no_external_validator(monkeypatch):
    monkeypatch.setattr(pdfa, "find_verapdf", lambda: None)


def _plain_pdf(path, title="Relatório anual", author="Ana") -> None:
    """Página com texto numa fonte embutida: um documento que pode virar PDF/A sem o
    Ghostscript."""
    register_fonts()
    c = rl_canvas.Canvas(str(path), pagesize=(300, 300))
    c.setTitle(title)
    c.setAuthor(author)
    c.setFont(SANS, 12)
    c.drawString(40, 200, "Conteúdo do relatório")
    c.showPage()
    c.save()


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

    result = ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="b")

    assert result.written, result.issues
    reader = PdfReader(str(path_out))
    assert list(reader.attachments.keys()) == []
    annots = [ref.get_object() for ref in reader.pages[0]["/Annots"]]
    link = next(a for a in annots if a["/Subtype"] == "/Link")
    assert "/A" not in link
    assert int(link["/F"]) & 4  # marcada para impressão
    assert result.fixed


def test_pdfa3_keeps_attachments_with_relationship(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)
    path_out = tmp_path / "out.pdf"

    result = ConvertToPDFA().run(str(path_in), str(path_out), part=3, conformance="b")

    assert result.written, result.issues
    reader = PdfReader(str(path_out))
    assert list(reader.attachments) == ["secreto.txt"]  # o PDF/A-3 permite anexos
    catalog = reader.trailer["/Root"]
    (spec,) = [ref.get_object() for ref in catalog["/AF"]]
    assert spec["/AFRelationship"] == "/Unspecified"
    assert spec["/EF"]["/F"].get_object()["/Subtype"] == "/text/plain"


def test_conversion_embeds_the_color_profile_and_merges_metadata(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in, title="Relatório anual", author="Ana")
    path_out = tmp_path / "out.pdf"

    ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="B")

    reader = PdfReader(str(path_out))
    (intent,) = [ref.get_object() for ref in reader.trailer["/Root"]["/OutputIntents"]]
    assert intent["/S"] == "/GTS_PDFA1"
    profile = intent["/DestOutputProfile"].get_object()
    assert profile["/N"] == 3 and profile.get_data()[36:40] == b"acsp"
    xmp = reader.xmp_metadata
    assert (str(xmp.pdfaid_part), xmp.pdfaid_conformance) == ("2", "B")
    # Antes o XMP inteiro era substituído só pela declaração, e o título sumia dele.
    assert xmp.dc_title == {"x-default": "Relatório anual"}
    assert xmp.dc_creator == ["Ana"]
    assert reader.metadata["/Title"] == "Relatório anual"
    assert str(reader.metadata["/Producer"]) == xmp.pdf_producer


def test_non_embedded_font_blocks_the_conversion_and_nothing_is_written(tmp_path):
    path_in = tmp_path / "helvetica.pdf"
    c = rl_canvas.Canvas(str(path_in))
    c.drawString(40, 700, "Helvetica não é embutida")
    c.save()
    path_out = tmp_path / "out.pdf"

    result = ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="B")

    assert not result.written
    assert not path_out.exists()
    assert any("Helvetica" in issue and "não embutidas" in issue for issue in result.issues)


def test_pdfa1_rejects_transparency(tmp_path):
    path_in = tmp_path / "transparente.pdf"
    register_fonts()
    c = rl_canvas.Canvas(str(path_in))
    c.setFont(SANS, 12)
    c.setFillAlpha(0.5)
    c.drawString(40, 700, "meio transparente")
    c.save()

    result = ConvertToPDFA().run(str(path_in), str(tmp_path / "a1.pdf"), part=1, conformance="B")
    assert not result.written
    assert any("transparência" in issue for issue in result.issues)

    assert ConvertToPDFA().run(str(path_in), str(tmp_path / "a2.pdf"), part=2, conformance="B").written


def test_level_a_requires_a_tagged_document(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)

    result = ConvertToPDFA().run(str(path_in), str(tmp_path / "out.pdf"), part=2, conformance="A")

    assert not result.written
    assert any("tagueado" in issue for issue in result.issues)


@pytest.mark.parametrize(("part", "conformance"), [(9, "B"), (2, "Z"), (1, "U")])
def test_invalid_part_and_conformance_are_rejected(tmp_path, part, conformance):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)

    with pytest.raises(ValueError):
        ConvertToPDFA().run(str(path_in), str(tmp_path / "out.pdf"), part=part, conformance=conformance)


def test_convert_to_pdfa_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ConvertToPDFA().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_hidden_annotation_is_removed(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)
    writer = PdfWriter(clone_from=str(path_in))
    writer.add_annotation(0, {"/Subtype": "/Link", "/Rect": [0, 0, 10, 10], "/F": 2})
    writer.write(str(path_in))
    path_out = tmp_path / "out.pdf"

    ConvertToPDFA().run(str(path_in), str(path_out))

    assert PdfReader(str(path_out)).pages[0].get("/Annots", []) == []


def test_validate_pdfa_flags_js_attachments_and_missing_declaration(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)

    result = ValidatePDFA().run(str(path_in), part=2, conformance="B")

    assert not result.is_valid
    assert any("JavaScript" in issue for issue in result.issues)
    assert any("anexos" in issue for issue in result.issues)
    assert any("não declaram" in issue for issue in result.issues)
    assert any("perfil de cor" in issue for issue in result.issues)


def test_validate_pdfa_passes_converted_document(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_js_and_attachment(path_in)
    path_out = tmp_path / "out.pdf"
    ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="b")

    result = ValidatePDFA().run(str(path_out), part=2, conformance="b")

    assert result.is_valid, result.issues
    assert result.issues == []


def test_declaration_alone_does_not_pass_validation(tmp_path):
    # Um arquivo que só declara PDF/A no XMP (o que a versão anterior gerava) não passa.
    from pypdf.xmp import XmpInformation

    path_in = tmp_path / "declarado.pdf"
    c = rl_canvas.Canvas(str(path_in))
    c.drawString(40, 700, "Helvetica")
    c.save()
    writer = PdfWriter(clone_from=str(path_in))
    xmp = XmpInformation.create()
    xmp.pdfaid_part = 2
    xmp.pdfaid_conformance = "B"
    writer.xmp_metadata = xmp
    writer.write(str(path_in))

    result = ValidatePDFA().run(str(path_in))

    assert not result.is_valid
    assert any("perfil de cor" in issue for issue in result.issues)
    assert any("não embutidas" in issue for issue in result.issues)


def test_verapdf_verdict_is_reported(tmp_path, monkeypatch):
    path_in = tmp_path / "out.pdf"
    _plain_pdf(tmp_path / "doc.pdf")
    ConvertToPDFA().run(str(tmp_path / "doc.pdf"), str(path_in))
    report = b"""<?xml version="1.0"?><report><jobs><job><validationReport profileName="PDF/A-2B"
      isCompliant="false"><details><rule clause="6.2.4.3" status="failed"><description>DeviceRGB
      sem OutputIntent</description></rule></details></validationReport></job></jobs></report>"""
    monkeypatch.setattr(pdfa, "find_verapdf", lambda: "verapdf")
    monkeypatch.setattr(pdfa, "run_cancellable", lambda *args, **kwargs: (1, report))

    result = ValidatePDFA().run(str(path_in))

    assert result.verapdf_used and result.verapdf_compliant is False
    assert not result.is_valid
    assert any("6.2.4.3" in issue for issue in result.issues)


def test_ghostscript_conversion_uses_the_color_profile(tmp_path, monkeypatch):
    path_in = tmp_path / "helvetica.pdf"
    c = rl_canvas.Canvas(str(path_in))
    c.drawString(40, 700, "Helvetica")
    c.save()
    commands = []

    def fake_gs(command, progress, timeout, program="", capture_stdout=False):
        commands.append(command)
        output = next(arg.split("=", 1)[1] for arg in command if arg.startswith("-sOutputFile="))
        _plain_pdf(output)  # o Ghostscript entregaria um PDF com as fontes embutidas
        return 0, b""

    monkeypatch.setattr(pdfa, "find_ghostscript", lambda: "gswin64c")
    monkeypatch.setattr(pdfa, "run_cancellable", fake_gs)
    path_out = tmp_path / "out.pdf"

    result = ConvertToPDFA().run(str(path_in), str(path_out), part=2, conformance="B", use_ghostscript=True)

    assert result.written and result.used_ghostscript
    assert "-dPDFA=2" in commands[0]
    assert any(arg.startswith("--permit-file-read=") and arg.endswith(".icc") for arg in commands[0])
    assert str(PdfReader(str(path_out)).xmp_metadata.pdfaid_part) == "2"


def test_lzw_streams_are_recoded(tmp_path):
    from pypdf.generic import StreamObject

    path_in = tmp_path / "doc.pdf"
    _plain_pdf(path_in)
    writer = PdfWriter(clone_from=str(path_in))
    page = writer.pages[0]
    content = page.get_contents()
    data = content.get_data()
    lzw = StreamObject()
    lzw._data = _lzw_encode(data)
    lzw[NameObject("/Filter")] = NameObject("/LZWDecode")
    page[NameObject("/Contents")] = writer._add_object(lzw)
    writer.write(str(path_in))
    path_out = tmp_path / "out.pdf"

    result = ConvertToPDFA().run(str(path_in), str(path_out))

    assert result.written, result.issues
    contents = PdfReader(str(path_out)).pages[0]["/Contents"].get_object()
    assert contents["/Filter"] == "/FlateDecode"
    assert "Conteúdo do relatório" in PdfReader(str(path_out)).pages[0].extract_text()


def _lzw_encode(data: bytes) -> bytes:
    """Codificador LZW mínimo, como o do PDF (códigos de 9 a 12 bits, EarlyChange)."""
    dictionary = {bytes([i]): i for i in range(256)}
    next_code, width = 258, 9
    codes = [(256, 9)]  # código de limpeza
    current = b""
    for byte in data:
        candidate = current + bytes([byte])
        if candidate in dictionary:
            current = candidate
            continue
        codes.append((dictionary[current], width))
        dictionary[candidate] = next_code
        next_code += 1
        if next_code >= (1 << width) - 1 and width < 12:
            width += 1
        current = bytes([byte])
    if current:
        codes.append((dictionary[current], width))
    codes.append((257, width))  # fim dos dados
    out, buffer, count = [], 0, 0
    for code, size in codes:
        buffer = (buffer << size) | code
        count += size
        while count >= 8:
            count -= 8
            out.append((buffer >> count) & 0xFF)
    if count:
        out.append((buffer << (8 - count)) & 0xFF)
    return bytes(out)
