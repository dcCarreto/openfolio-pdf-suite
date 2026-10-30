"""Testes de ui/pages/redaction_page.py: confirmação antes de aplicar redação (irreversível)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.redaction import RedactionRect, SanitizeReport, find_residual_risks
from ui.document_session import DocumentSession
from ui.tasks import wait_for_tasks
from ui.pages.redaction_page import RedactionPage, format_sanitize_report
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
    page.redact_output_picker.restore((str(tmp_path / "out.pdf"), session.source_path(), False))
    return page


def test_apply_redaction_aborts_when_user_declines_confirmation(monkeypatch, tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)

    page._apply_redaction()
    wait_for_tasks()

    assert not (tmp_path / "out.pdf").exists()


def test_apply_redaction_proceeds_when_user_confirms(monkeypatch, tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    page._apply_redaction()
    wait_for_tasks()

    assert (tmp_path / "out.pdf").exists()


def test_apply_redaction_also_sanitizes_by_default(monkeypatch, tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)
    assert page.also_sanitize_checkbox.isChecked()
    messages = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: messages.append(args[2]))

    page._apply_redaction()
    wait_for_tasks()

    assert find_residual_risks(str(tmp_path / "out.pdf")) == []
    assert "1 página redigida" in messages[0]
    assert "Nada perigoso" in messages[0] or "Removido:" in messages[0]


def test_pending_list_describes_each_area_and_removes_the_selected_ones(tmp_path):
    _app()
    page = _build_page_with_pending_rect(tmp_path)  # uma área marcada à mão
    state = page.redaction_state
    detected = RedactionRect(page_index=0, left=10, bottom=10, right=50, top=30, kind="cpf", text="123.456.789-00")
    state.add_pending(detected)

    texts = [page.pending_list.item(i).text() for i in range(page.pending_list.count())]
    assert len(texts) == 2
    assert any("área marcada à mão" in text for text in texts)
    assert any("CPF: 123.456.789-00" in text for text in texts)

    row = next(i for i, text in enumerate(texts) if "CPF" in text)
    page.pending_list.setCurrentRow(row)
    assert state.selected() == detected  # o visualizador destaca e mostra a página dela

    page._remove_selected_pending()
    assert state.pending() == [RedactionRect(page_index=0, left=0, bottom=0, right=100, top=100)]
    assert page.pending_list.count() == 1
    assert page.pending_list.item(0).data(Qt.ItemDataRole.UserRole) == state.pending()[0]


def test_format_sanitize_report_lists_only_what_was_removed():
    _app()
    text = format_sanitize_report(SanitizeReport(javascript=2, embedded_files=1, metadata_removed=True))

    assert "2 scripts ou ações de JavaScript" in text
    assert "1 arquivo embutido" in text
    assert "metadados do documento" in text
    assert "anotação" not in text
    assert format_sanitize_report(SanitizeReport()) == "Nada perigoso foi encontrado no documento."


def test_searching_a_text_marks_every_occurrence_for_review(monkeypatch, tmp_path):
    _app()
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in)
    session = DocumentSession()
    session.open(str(path_in))
    page = RedactionPage(session, RedactionState())
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))

    page.search_text_edit.setText("CONTEUDO")
    page.search_text_edit.returnPressed.emit()  # Enter no campo também procura
    assert wait_for_tasks()

    assert [page.pending_list.item(i).text() for i in range(page.pending_list.count())] == [
        "Página 1 — Texto buscado: conteudo"
    ]
    assert shown and "1 ocorrência encontrada" in shown[0]
