"""Documento de trabalho pela janela (M01): aplicar, desfazer, salvar e fechar."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.main_window import MainWindow
from ui.tasks import wait_for_tasks


@pytest.fixture
def window(tmp_path):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    yield window
    window.session.set_discard_confirmation(None)
    window.close()


def _three_pages(path):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=300, height=300)
    writer.write(str(path))
    return str(path)


def _apply_watermark(window, text="CONFIDENCIAL"):
    row = window._row_of["WatermarkPage"]
    window.sidebar.setCurrentRow(row)
    page = window._ensure_page(row)
    page.text_edit.setText(text)
    page._apply()
    assert wait_for_tasks()


def test_tool_result_goes_to_the_open_document(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    source = _three_pages(tmp_path / "contrato.pdf")
    window.session.open(source)
    window.viewer._show_single_page(2)

    _apply_watermark(window)

    session = window.session
    assert session.source_path() == source and session.path() != source
    assert "CONFIDENCIAL" in PdfReader(session.path()).pages[0].extract_text()
    assert "CONFIDENCIAL" not in PdfReader(source).pages[0].extract_text()  # nada salvo ainda
    assert window.windowTitle().startswith("contrato.pdf *")
    assert window._undo_action.isEnabled() and "Marca" in window._undo_action.text()
    assert window.viewer._current_page == 2  # continua na página em que estava
    assert not list(tmp_path.glob("contrato_*"))

    window._undo_action.trigger()
    assert session.path() == source and not session.is_modified()

    window._redo_action.trigger()
    window._save_action.trigger()
    assert "CONFIDENCIAL" in PdfReader(source).pages[0].extract_text()
    assert window.windowTitle().startswith("contrato.pdf —")


def test_closing_with_unsaved_changes_asks(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    window.session.open(_three_pages(tmp_path / "doc.pdf"))
    _apply_watermark(window)
    asked = []

    def answer(*args, **kwargs):
        asked.append(args[1])
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", answer)
    window.show()

    window.close()

    assert asked and window.isVisible()  # cancelou: a janela continua aberta
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()
    assert not window.isVisible()


def test_saving_to_another_file_opens_that_file(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    source = _three_pages(tmp_path / "doc.pdf")
    window.session.open(source)
    row = window._row_of["WatermarkPage"]
    page = window._ensure_page(row)
    target = str(tmp_path / "copia_com_marca.pdf")
    page.output_picker.restore((target, source, False))

    _apply_watermark(window)

    assert window.session.source_path() == target and not window.session.is_modified()
