"""Testes de ui/pages/redaction_page.py: confirmação antes de aplicar redação (irreversível)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.redaction import RedactionRect
from ui.document_session import DocumentSession
from ui.pages.redaction_page import RedactionPage
from ui.redaction_state import RedactionState


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_pdf(path) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(300, 300))
    canvas.drawString(40, 250, "conteudo qualquer")
    canvas.showPage()
    canvas.save()


def _build_page_with_pending_rect(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in)

    session = DocumentSession()
    session.open(str(path_in))
    redaction_state = RedactionState()
    redaction_state.add_pending(RedactionRect(page_index=0, left=0, bottom=0, right=100, top=100))

    page = RedactionPage(session, redaction_state)
    page.redact_output_picker._path = str(tmp_path / "out.pdf")
    return page


def test_apply_redaction_aborts_when_user_declines_confirmation(monkeypatch, tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)

    page._apply_redaction()

    assert not (tmp_path / "out.pdf").exists()


def test_apply_redaction_proceeds_when_user_confirms(monkeypatch, tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    page._apply_redaction()

    assert (tmp_path / "out.pdf").exists()
