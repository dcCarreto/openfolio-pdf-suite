import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.protect import ProtectPDF, UnlockPDF


def test_protect_encrypts_pdf(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200)])
    output_path = tmp_path / "protected.pdf"

    ProtectPDF().run(str(pdf_path), str(output_path), password="segredo123")

    reader = PdfReader(str(output_path))
    assert reader.is_encrypted


def test_unlock_removes_password(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200)])
    protected_path = tmp_path / "protected.pdf"
    unlocked_path = tmp_path / "unlocked.pdf"

    ProtectPDF().run(str(pdf_path), str(protected_path), password="segredo123")
    UnlockPDF().run(str(protected_path), str(unlocked_path), password="segredo123")

    reader = PdfReader(str(unlocked_path))
    assert not reader.is_encrypted
    assert len(reader.pages) == 2


def test_unlock_with_wrong_password_raises(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    protected_path = tmp_path / "protected.pdf"
    unlocked_path = tmp_path / "unlocked.pdf"

    ProtectPDF().run(str(pdf_path), str(protected_path), password="segredo123")

    with pytest.raises(ValueError):
        UnlockPDF().run(str(protected_path), str(unlocked_path), password="senha-errada")


def test_protect_rejects_already_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    output_path = tmp_path / "out.pdf"

    with pytest.raises(EncryptedPDFError):
        ProtectPDF().run(str(encrypted_path), str(output_path), password="outra-senha")
