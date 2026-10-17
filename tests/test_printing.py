"""Impressão (A01): páginas escolhidas, ajuste ao papel, permissão do autor e a janela."""

import faulthandler
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPageRanges
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from core.base import RestrictedPDFError
from core.progress import OperationCancelled, Progress
from ui.main_window import MainWindow
from ui.printing import pages_to_print, print_pages
from ui.tasks import wait_for_tasks


@pytest.fixture(autouse=True)
def _quiet_faulthandler():
    """No Windows, criar um QPrinter consulta a impressora padrão por COM, que levanta e
    trata a exceção 0x80040155; o faulthandler do pytest a despeja como "fatal" (não é)."""
    was_enabled = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if was_enabled:
        faulthandler.enable(file=sys.__stderr__)


@pytest.fixture
def source(tmp_path):
    """Página 1 em paisagem com a metade esquerda preta; páginas 2 e 3 em retrato."""
    path = tmp_path / "origem.pdf"
    canvas = rl_canvas.Canvas(str(path))
    canvas.setPageSize((800, 400))
    canvas.rect(0, 0, 400, 400, fill=1)
    canvas.showPage()
    for number in (2, 3):
        canvas.setPageSize((400, 600))
        canvas.drawString(50, 500, f"Pagina {number}")
        canvas.showPage()
    canvas.save()
    return str(path)


def _pdf_printer(path) -> QPrinter:
    QApplication.instance() or QApplication([])
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    return printer


def test_prints_every_page_fitted_and_turned_to_the_paper(source, tmp_path):
    output = tmp_path / "impresso.pdf"
    assert print_pages(source, _pdf_printer(output), [0, 1, 2]) == 3

    document = pdfium.PdfDocument(str(output))
    try:
        assert len(document) == 3
        width, height = document[0].get_size()
        assert height > width  # papel em retrato
        image = document[0].render(scale=0.5).to_pil().convert("L")
        # A página em paisagem é girada para caber: a metade preta (esquerda) fica em cima.
        assert image.getpixel((image.width // 2, image.height // 3)) < 60
        assert image.getpixel((image.width // 2, image.height * 2 // 3)) > 200
    finally:
        document.close()


def test_pages_chosen_in_the_dialog(tmp_path):
    printer = _pdf_printer(tmp_path / "x.pdf")
    assert pages_to_print(printer, 5, current_page=2, selected_pages=[]) == [0, 1, 2, 3, 4]

    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    ranges = QPageRanges()
    ranges.addRange(1, 2)
    ranges.addPage(5)
    printer.setPageRanges(ranges)
    assert pages_to_print(printer, 5, current_page=2, selected_pages=[]) == [0, 1, 4]

    printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
    assert pages_to_print(printer, 5, current_page=2, selected_pages=[]) == [2]

    printer.setPrintRange(QPrinter.PrintRange.Selection)
    assert pages_to_print(printer, 5, current_page=2, selected_pages=[3, 1, 9]) == [1, 3]


def test_copies_are_printed_when_the_driver_does_not_make_them(source, tmp_path, monkeypatch):
    output = tmp_path / "copias.pdf"
    printer = _pdf_printer(output)
    printer.setCopyCount(2)
    monkeypatch.setattr(QPrinter, "supportsMultipleCopies", lambda self: False)
    assert print_pages(source, printer, [1]) == 2
    assert len(PdfReader(str(output)).pages) == 2


def test_refuses_when_the_author_does_not_allow_printing(source, tmp_path):
    restricted = tmp_path / "sem_impressao.pdf"
    writer = PdfWriter(clone_from=source)
    writer.encrypt(
        user_password="",
        owner_password="dono",
        permissions_flag=UserAccessPermissions.all() & ~UserAccessPermissions.PRINT,
        algorithm="AES-256",
    )
    writer.write(str(restricted))
    output = tmp_path / "nada.pdf"
    with pytest.raises(RestrictedPDFError, match="imprimi-lo"):
        print_pages(str(restricted), _pdf_printer(output), [0])
    assert not output.exists()


def test_cancelling_stops_printing(source, tmp_path):
    progress = Progress()
    progress.cancel()
    with pytest.raises(OperationCancelled):
        print_pages(source, _pdf_printer(tmp_path / "cancelado.pdf"), [0, 1], progress)


def test_window_prints_the_working_document(source, tmp_path):
    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    try:
        assert not window._print_action.isEnabled()
        window.session.open(source)
        assert window._print_action.isEnabled()

        output = tmp_path / "janela.pdf"
        printer = _pdf_printer(output)
        printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
        window.session.set_current_page(1)
        assert window.start_printing(printer, 3)
        assert wait_for_tasks()
        assert len(PdfReader(str(output)).pages) == 1
        assert "1" in window.statusBar().currentMessage()
    finally:
        window.close()
