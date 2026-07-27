"""Testes de core/redaction.py: redação real (rasterização) e sanitização de PDFs."""

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import ArrayObject, FloatObject
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.redaction import RedactDocument, RedactionRect, SanitizeDocument


def _make_pdf_with_text(path, texts: list[str]) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.setFont("Helvetica", 16)
    y = 250
    for text in texts:
        canvas.drawString(40, y, text)
        y -= 40
    canvas.showPage()
    canvas.save()


def test_redact_wipes_all_text_from_marked_pages(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Segredo confidencial", "Outra linha qualquer"])

    before = PdfReader(str(path_in)).pages[0].extract_text()
    assert "Segredo" in before

    rect = RedactionRect(page_index=0, left=40, bottom=230, right=250, top=260)
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [rect])

    assert pages_redacted == 1
    after = PdfReader(str(path_out)).pages[0].extract_text()
    assert after.strip() == ""  # a página inteira virou imagem: nada de texto sobra


def test_redact_leaves_unmarked_pages_untouched(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"

    writer = PdfWriter()
    for text in ("Primeira pagina com dados", "Segunda pagina sem marcacao"):
        buffer_path = tmp_path / f"_{text[:4]}.pdf"
        _make_pdf_with_text(buffer_path, [text])
        writer.add_page(PdfReader(str(buffer_path)).pages[0])
    with open(path_in, "wb") as f:
        writer.write(f)

    rect = RedactionRect(page_index=0, left=0, bottom=0, right=400, top=300)
    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [rect])

    assert pages_redacted == 1
    reader = PdfReader(str(path_out))
    assert reader.pages[0].extract_text().strip() == ""
    assert "Segunda pagina sem marcacao" in reader.pages[1].extract_text()


def test_redact_with_no_rects_copies_document_unchanged(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Nada marcado"])

    pages_redacted = RedactDocument().run(str(path_in), str(path_out), [])

    assert pages_redacted == 0
    assert "Nada marcado" in PdfReader(str(path_out)).pages[0].extract_text()


def test_redact_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        RedactDocument().run(str(encrypted_path), str(path_out), [])


def _pdf_with_hidden_data(path) -> None:
    src_text = str(path).replace(".pdf", "_src.pdf")
    _make_pdf_with_text(src_text, ["Conteudo visivel do documento"])

    quads = ArrayObject([FloatObject(v) for v in [40, 260, 200, 260, 40, 240, 200, 240]])
    writer = PdfWriter(clone_from=src_text)
    writer.add_metadata({"/Title": "Segredo Confidencial", "/Author": "Fulano de Tal"})
    writer.add_js('app.alert("oi");')
    writer.add_attachment("secreto.txt", b"dados sensiveis anexados")
    writer.add_annotation(
        page_number=0,
        annotation=Highlight(rect=(40, 240, 200, 260), quad_points=quads, highlight_color="ffeb3b"),
    )
    writer.add_annotation(
        page_number=0,
        annotation={
            "/Subtype": "/Link",
            "/Rect": [40, 200, 200, 220],
            "/A": {"/S": "/JavaScript", "/JS": 'app.alert("annotation js");'},
        },
    )
    with open(path, "wb") as f:
        writer.write(f)


def test_sanitize_default_removes_metadata_js_and_attachments_but_keeps_annotations(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out))

    reader = PdfReader(str(path_out))
    assert reader.metadata.get("/Title") is None
    assert list(reader.attachments.keys()) == []
    assert reader.pages[0].get("/Annots") is not None
    assert "Conteudo visivel do documento" in reader.pages[0].extract_text()


def test_sanitize_removes_javascript_embedded_in_annotation_actions(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out))

    reader = PdfReader(str(path_out))
    annots = [ref.get_object() for ref in reader.pages[0]["/Annots"]]
    link = next(a for a in annots if a["/Subtype"] == "/Link")

    # A anotação de link continua lá (remove_annotations=False por padrão), mas a ação de
    # JavaScript embutida nela foi removida — é exatamente o conteúdo que "sanitizar" promete
    # sempre eliminar, mesmo quando as anotações em si são preservadas.
    assert "/A" not in link
    assert any(a["/Subtype"] == "/Highlight" for a in annots)


def test_sanitize_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        SanitizeDocument().run(str(encrypted_path), str(path_out))


def test_sanitize_can_keep_metadata_and_remove_annotations(tmp_path):
    path_in = tmp_path / "loaded.pdf"
    _pdf_with_hidden_data(path_in)
    path_out = tmp_path / "out.pdf"

    SanitizeDocument().run(str(path_in), str(path_out), remove_metadata=False, remove_annotations=True)

    reader = PdfReader(str(path_out))
    assert reader.metadata.get("/Title") == "Segredo Confidencial"
    assert reader.pages[0].get("/Annots") is None
    assert list(reader.attachments.keys()) == []  # anexos são sempre removidos
    assert "Conteudo visivel do documento" in reader.pages[0].extract_text()
