import pytest
from pypdf import PdfReader
from pypdf.constants import UserAccessPermissions as Perm

from core.base import EncryptedPDFError
from core.protect import PDFPermissions, ProtectPDF, UnlockPDF


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


def test_protect_without_permissions_allows_everything(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "protected.pdf"

    ProtectPDF().run(str(pdf_path), str(output_path), password="segredo123")

    reader = PdfReader(str(output_path))
    assert reader.decrypt("segredo123")
    assert reader.user_access_permissions & Perm.PRINT
    assert reader.user_access_permissions & Perm.MODIFY


def test_protect_with_permissions_restricts_user_password_access(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "protected.pdf"
    permissions = PDFPermissions(
        allow_printing=False,
        allow_modify=False,
        allow_copy=False,
        allow_annotations=False,
        allow_fill_forms=True,
    )

    ProtectPDF().run(
        str(pdf_path),
        str(output_path),
        password="",
        owner_password="dono123",
        permissions=permissions,
    )

    reader = PdfReader(str(output_path))
    assert reader.decrypt("")  # senha de usuário vazia: abre sem pedir senha
    assert not reader.user_access_permissions & Perm.PRINT
    assert not reader.user_access_permissions & Perm.MODIFY
    assert not reader.user_access_permissions & Perm.EXTRACT
    assert reader.user_access_permissions & Perm.FILL_FORM_FIELDS

    # a senha de proprietário sempre tem acesso total, mesmo com permissões restritas
    reader_as_owner = PdfReader(str(output_path))
    assert reader_as_owner.decrypt("dono123") == 2  # 2 = decodificado como proprietário
