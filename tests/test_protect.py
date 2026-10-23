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


def _restricted_pdf(tmp_path, *, allow_copy: bool):
    from reportlab.pdfgen import canvas as rl_canvas

    source = tmp_path / "source.pdf"
    canvas = rl_canvas.Canvas(str(source), pagesize=(300, 300))
    canvas.drawString(40, 200, "Extrato bancario")
    canvas.save()
    restricted = tmp_path / "restricted.pdf"
    ProtectPDF().run(
        str(source),
        str(restricted),
        password="",
        owner_password="dono123",
        permissions=PDFPermissions(allow_modify=False, allow_copy=allow_copy),
    )
    return restricted


def test_restricted_pdf_works_in_reading_tools(tmp_path):
    # Um PDF que abre sem senha (só com restrições) era recusado por todas as ferramentas.
    from core.metadata import ReadMetadata

    restricted = _restricted_pdf(tmp_path, allow_copy=True)

    assert ReadMetadata().run(str(restricted))["title"] == "untitled"


def test_restricted_pdf_extraction_respects_the_copy_permission(tmp_path):
    from core.base import RestrictedPDFError
    from core.extract_text import ExtractText

    (tmp_path / "a").mkdir()
    allowed = _restricted_pdf(tmp_path / "a", allow_copy=True)
    ExtractText().run(str(allowed), str(tmp_path / "a" / "texto.txt"))
    assert "Extrato" in (tmp_path / "a" / "texto.txt").read_text(encoding="utf-8")

    (tmp_path / "b").mkdir()
    denied = _restricted_pdf(tmp_path / "b", allow_copy=False)
    with pytest.raises(RestrictedPDFError, match="não permite copiar"):
        ExtractText().run(str(denied), str(tmp_path / "b" / "texto.txt"))


def test_restricted_pdf_modification_explains_how_to_unlock(tmp_path):
    from core.base import RestrictedPDFError
    from core.watermark import AddWatermark

    restricted = _restricted_pdf(tmp_path, allow_copy=True)

    with pytest.raises(RestrictedPDFError, match="senha de permissões"):
        AddWatermark().run(str(restricted), str(tmp_path / "out.pdf"), text="X")

    unlocked = tmp_path / "unlocked.pdf"
    UnlockPDF().run(str(restricted), str(unlocked), password="dono123")
    AddWatermark().run(str(unlocked), str(tmp_path / "out.pdf"), text="X")


def test_password_typed_in_the_viewer_is_reused_by_reading_tools(make_encrypted_pdf):
    from core.base import forget_password, remember_password
    from core.metadata import ReadMetadata

    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    with pytest.raises(EncryptedPDFError):
        ReadMetadata().run(str(encrypted_path))

    remember_password(encrypted_path, "segredo123")
    try:
        assert ReadMetadata().run(str(encrypted_path))["title"] == ""
    finally:
        forget_password(encrypted_path)
