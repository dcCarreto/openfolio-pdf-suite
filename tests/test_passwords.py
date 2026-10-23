"""Senhas (M32): os campos ficam vazios depois do uso, a troca de idioma não as copia e a
senha de abertura sai da memória quando o documento fecha."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from core.base import known_password, remember_password
from ui.document_session import DocumentSession
from ui.tasks import wait_for_tasks


def _app():
    return QApplication.instance() or QApplication([])


def test_protecting_and_unlocking_clear_the_password_fields(make_pdf, tmp_path, monkeypatch):
    from pypdf import PdfReader

    from ui.pages.protect_page import ProtectPage

    _app()
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    session = DocumentSession()
    session.open(str(make_pdf("doc.pdf", [(200, 200)])))
    page = ProtectPage(session)
    protected = tmp_path / "protegido.pdf"
    monkeypatch.setattr(page.protect_output_picker, "path", lambda: str(protected))

    page.protect_password_edit.setText("segredo")
    page.protect_confirm_password_edit.setText("segredo")
    page._protect()
    assert (page.protect_password_edit.text(), page.protect_confirm_password_edit.text()) == ("", "")
    assert wait_for_tasks()
    reader = PdfReader(str(protected))
    assert reader.is_encrypted and reader.decrypt("segredo")  # gravado com a senha lida antes de limpar

    unlocked = tmp_path / "aberto.pdf"
    monkeypatch.setattr(page.unlock_output_picker, "path", lambda: str(unlocked))
    page.unlock_password_edit.setText("segredo")
    page._unlock()
    assert page.unlock_password_edit.text() == ""
    assert wait_for_tasks()
    assert unlocked.exists()


def test_language_change_does_not_copy_passwords(make_pdf):
    from ui.pages.protect_page import ProtectPage
    from ui.widget_state import capture_state, restore_state

    _app()
    session = DocumentSession()
    page = ProtectPage(session)
    page.unlock_password_edit.setText("segredo")

    rebuilt = ProtectPage(session)
    restore_state(rebuilt, capture_state(page))

    assert rebuilt.unlock_password_edit.text() == ""
    assert "segredo" not in repr(capture_state(page))


def test_the_open_password_is_forgotten_when_the_document_closes(make_encrypted_pdf, make_pdf, monkeypatch):
    _app()
    encrypted = make_encrypted_pdf("protegido.pdf", [(200, 200)])
    session = DocumentSession()
    session.open(str(encrypted))
    remember_password(str(encrypted), "segredo123")  # como o visualizador faz ao abrir
    version = session.new_version_path()
    with open(version, "wb") as file:
        file.write(encrypted.read_bytes())
    session.open(version)
    assert known_password(version) == "segredo123"  # a versão herda a senha

    session.open(str(make_pdf("outro.pdf", [(200, 200)])))

    assert known_password(str(encrypted)) is None and known_password(version) is None
