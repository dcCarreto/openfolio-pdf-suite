"""Testes de core/attachments.py: listar, adicionar, remover e extrair anexos embutidos."""

import pytest
from pypdf import PdfReader, PdfWriter

from core.attachments import AddAttachment, ExtractAttachments, ListAttachments, RemoveAttachment
from core.base import EncryptedPDFError


def _make_plain_pdf(path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_add_and_list_attachment(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_path = tmp_path / "notas.txt"
    attachment_path.write_bytes(b"conteudo do anexo")
    output_path = tmp_path / "out.pdf"

    AddAttachment().run(str(pdf_path), str(output_path), str(attachment_path))

    attachments = ListAttachments().run(str(output_path))
    assert len(attachments) == 1
    assert attachments[0].name == "notas.txt"
    assert attachments[0].size == len(b"conteudo do anexo")


def test_list_attachments_empty_for_pdf_without_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    assert ListAttachments().run(str(pdf_path)) == []


def test_list_attachments_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ListAttachments().run(str(encrypted_path))


def test_add_attachment_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    attachment_path = tmp_path / "notas.txt"
    attachment_path.write_bytes(b"x")

    with pytest.raises(EncryptedPDFError):
        AddAttachment().run(str(encrypted_path), str(tmp_path / "out.pdf"), str(attachment_path))


def test_extract_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_path = tmp_path / "dados.csv"
    attachment_path.write_bytes(b"a,b,c\n1,2,3")
    with_attachment = tmp_path / "with_attachment.pdf"
    AddAttachment().run(str(pdf_path), str(with_attachment), str(attachment_path))

    output_dir = tmp_path / "extracted"
    output_paths = ExtractAttachments().run(str(with_attachment), str(output_dir))

    assert len(output_paths) == 1
    from pathlib import Path
    assert Path(output_paths[0]).read_bytes() == b"a,b,c\n1,2,3"


def test_extract_attachments_empty_for_pdf_without_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    assert ExtractAttachments().run(str(pdf_path), str(tmp_path / "out")) == []


def test_remove_attachment(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_a = tmp_path / "a.txt"
    attachment_a.write_bytes(b"A")
    attachment_b = tmp_path / "b.txt"
    attachment_b.write_bytes(b"B")

    step1 = tmp_path / "step1.pdf"
    AddAttachment().run(str(pdf_path), str(step1), str(attachment_a))
    step2 = tmp_path / "step2.pdf"
    AddAttachment().run(str(step1), str(step2), str(attachment_b))

    output_path = tmp_path / "out.pdf"
    RemoveAttachment().run(str(step2), str(output_path), name="a.txt")

    attachments = ListAttachments().run(str(output_path))
    assert [a.name for a in attachments] == ["b.txt"]


def test_remove_attachment_rejects_unknown_name(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    with pytest.raises(ValueError):
        RemoveAttachment().run(str(pdf_path), str(tmp_path / "out.pdf"), name="inexistente.txt")


def test_remove_attachment_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        RemoveAttachment().run(str(encrypted_path), str(tmp_path / "out.pdf"), name="x.txt")
