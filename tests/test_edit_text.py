"""Testes de core/edit_text.py: "edição" de texto por cobrir e reescrever."""

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.edit_text import EditTextArea, TextEditRect


def _make_pdf_with_text(path, texts: list[str]) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.setFont("Helvetica", 16)
    y = 250
    for text in texts:
        canvas.drawString(40, y, text)
        y -= 40
    canvas.showPage()
    canvas.save()


def test_edit_text_area_replaces_old_text_with_new(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Valor antigo: 100", "Outra linha qualquer"])

    edit = TextEditRect(
        page_index=0, left=40, bottom=230, right=250, top=260, new_text="Valor novo: 200"
    )
    pages_edited = EditTextArea().run(str(path_in), str(path_out), [edit])

    assert pages_edited == 1
    after = PdfReader(str(path_out)).pages[0].extract_text()
    assert "Valor antigo" not in after
    assert "Valor novo: 200" in after


def test_edit_text_area_leaves_unmarked_pages_untouched(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"

    from pypdf import PdfReader as _R
    from pypdf import PdfWriter

    writer = PdfWriter()
    for text in ("Primeira pagina", "Segunda pagina sem edicao"):
        buffer_path = tmp_path / f"_{text[:4]}.pdf"
        _make_pdf_with_text(buffer_path, [text])
        writer.add_page(_R(str(buffer_path)).pages[0])
    with open(path_in, "wb") as f:
        writer.write(f)

    edit = TextEditRect(page_index=0, left=0, bottom=0, right=400, top=300, new_text="Editado")
    pages_edited = EditTextArea().run(str(path_in), str(path_out), [edit])

    assert pages_edited == 1
    reader = PdfReader(str(path_out))
    assert "Segunda pagina sem edicao" in reader.pages[1].extract_text()


def test_edit_text_area_with_no_edits_copies_document_unchanged(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_out.pdf"
    _make_pdf_with_text(path_in, ["Nada editado"])

    pages_edited = EditTextArea().run(str(path_in), str(path_out), [])

    assert pages_edited == 0
    assert "Nada editado" in PdfReader(str(path_out)).pages[0].extract_text()


def test_edit_text_area_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_out = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        EditTextArea().run(str(encrypted_path), str(path_out), [])
