"""Mensagens de erro para o usuário (M03)."""

import errno
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from core.messages import Message
from ui import i18n
from ui.errors import describe_error, show_error


def test_known_errors_become_plain_sentences():
    message, details = describe_error(PermissionError(13, "Permission denied", r"C:\docs\contrato.pdf"))
    assert "contrato.pdf" in message and "outro programa" in message and "Permission denied" in details

    message, _ = describe_error(FileNotFoundError(2, "No such file", "sumiu.pdf"))
    assert message == "O arquivo não foi encontrado: sumiu.pdf"

    message, _ = describe_error(OSError(errno.ENOSPC, "No space left on device"))
    assert "espaço" in message


def test_corrupted_pdf_has_a_friendly_message_and_technical_details():
    from pypdf.errors import PdfReadError

    message, details = describe_error(PdfReadError("EOF marker not found"))

    assert "corrompido" in message
    assert "EOF marker not found" in details


def test_app_messages_are_shown_as_they_are_and_translated():
    message, details = describe_error(ValueError(Message("A camada {number} não existe: o documento tem {count} camada(s).", number=3, count=1)))
    assert message.startswith("A camada 3") and details is None

    i18n.set_language(i18n.EN_US)
    try:
        assert describe_error(ValueError("Senha incorreta."))[0] == "Wrong password."
    finally:
        i18n.set_language(i18n.PT_BR)


def test_unexpected_errors_keep_the_traceback_in_the_details(monkeypatch):
    QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append((self.text(), self.detailedText())))

    try:
        {}["chave"]
    except KeyError as exc:
        show_error(None, "Teste", "Falha: {error}", exc)

    (text, details), = shown
    assert text == "Falha: Ocorreu um erro inesperado."
    assert "KeyError" in details and "Traceback" in details
