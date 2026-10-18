"""Processamento em lote (A05): BatchProcess e a aba Processar em lote."""

import csv
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication, QFileDialog

from core.batch import BatchProcess, pdfs_in_folder
from core.progress import OperationCancelled, Progress
from core.watermark import AddWatermark
from ui.document_session import DocumentSession
from ui.pages.batch_page import REPORT_NAME, BatchPage
from ui.tasks import wait_for_tasks


@pytest.fixture
def folder(make_pdf, tmp_path):
    source = tmp_path / "entrada"
    source.mkdir()
    for name in ("b.pdf", "A.PDF"):
        make_pdf(name, [(200, 200)]).replace(source / name)
    (source / "quebrado.pdf").write_bytes(b"isto nao e um pdf")
    (source / "notas.txt").write_text("fora do lote")
    return source


def _watermark(src, dst, _progress):
    AddWatermark().run(src, dst, "LOTE")


def test_pdfs_in_folder_lists_only_pdfs_alphabetically(folder):
    assert [os.path.basename(path) for path in pdfs_in_folder(str(folder))] == ["A.PDF", "b.pdf", "quebrado.pdf"]


def test_batch_keeps_going_after_a_failure_and_never_overwrites(folder, tmp_path):
    output = tmp_path / "saida"
    output.mkdir()
    (output / "b_marca.pdf").write_bytes(b"ja existia")

    results = BatchProcess().run(pdfs_in_folder(str(folder)), str(output), _watermark, "marca")

    assert [(os.path.basename(r.output_path), r.error is None) for r in results] == [
        ("A_marca.pdf", True),
        ("b_marca (2).pdf", True),
        ("", False),
    ]
    assert (output / "b_marca.pdf").read_bytes() == b"ja existia"
    assert "LOTE" in PdfReader(str(output / "A_marca.pdf")).pages[0].extract_text()


def test_cancelling_stops_the_batch(folder, tmp_path):
    cancel = threading.Event()

    def cancel_after_first(src, dst, progress):
        _watermark(src, dst, progress)
        cancel.set()

    with pytest.raises(OperationCancelled):
        BatchProcess().run(
            pdfs_in_folder(str(folder)), str(tmp_path / "saida"), cancel_after_first, "x", Progress(cancel_event=cancel)
        )
    assert os.listdir(tmp_path / "saida") == ["A_x.pdf"]


def test_batch_page_processes_the_folder_and_saves_a_report(folder, monkeypatch):
    QApplication.instance() or QApplication([])
    page = BatchPage(DocumentSession())
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(folder))
    page.input_picker._browse()
    assert page.found_label.text() == "3 PDF(s) na pasta."

    page.operation_combo.setCurrentIndex(3)  # Numerar páginas
    page.process_button.click()
    assert wait_for_tasks()

    output = folder / "processados"
    assert sorted(os.listdir(output)) == ["A_numerado.pdf", "b_numerado.pdf", REPORT_NAME]
    assert page.results_table.rowCount() == 3
    assert page.results_table.item(2, 1).text() == "Falhou: O PDF parece estar corrompido ou não é um PDF válido."
    assert "2 de 3" in page.status_label.text() and "Falharam: 1." in page.status_label.text()
    with open(output / REPORT_NAME, encoding="utf-8-sig") as file:
        rows = list(csv.reader(file))
    assert rows[0] == ["Arquivo", "Resultado"] and rows[1] == ["A.PDF", "Salvo como A_numerado.pdf"]


def test_batch_page_asks_for_the_password_before_protecting(folder, monkeypatch):
    QApplication.instance() or QApplication([])
    page = BatchPage(DocumentSession())
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(folder))
    page.input_picker._browse()
    page.operation_combo.setCurrentIndex(4)  # Proteger com senha
    page.process_button.click()
    assert page.status_label.text() == "Digite a senha."
    assert not (folder / "processados").exists()


def test_ocr_cannot_start_without_tesseract(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr("ui.pages.batch_page.find_tesseract", lambda: None)
    page = BatchPage(DocumentSession())
    page.operation_combo.setCurrentIndex(1)  # OCR
    assert not page.process_button.isEnabled()
    page.operation_combo.setCurrentIndex(0)
    assert page.process_button.isEnabled()
