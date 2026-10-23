"""Limpeza de escaneados (A08): CleanScannedPages e a aba Limpar escaneados."""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from PySide6.QtWidgets import QApplication
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from core.scan_cleanup import CleanScannedPages, ink_mask, skew_angle
from ui.document_session import DocumentSession
from ui.pages.scan_cleanup_page import ScanCleanupPage
from ui.tasks import wait_for_tasks


def _scan(angle=0.0, text=True, specks=0):
    """Uma "página escaneada" A4 a 100 DPI: papel acinzentado, linhas de "palavras" e
    poeira, girada `angle` graus."""
    image = Image.new("L", (827, 1169), 235)
    draw = ImageDraw.Draw(image)
    if text:
        for line in range(20):
            y = 250 + line * 30
            for word in range(8):
                draw.rectangle((180 + word * 60, y, 180 + word * 60 + 45, y + 12), fill=20)
    image = image.rotate(angle, fillcolor=235)
    rnd = random.Random(1)
    for _ in range(specks):
        image.putpixel((rnd.randrange(image.width), rnd.randrange(image.height)), 0)
    return image


def _scan_pdf(path, images, size=(595, 842)):
    canvas = rl_canvas.Canvas(str(path), pagesize=size)
    for image in images:
        canvas.drawImage(ImageReader(image), 0, 0, *size)
        canvas.showPage()
    canvas.save()
    return path


def _residual_skew(path, index):
    document = pdfium.PdfDocument(str(path))
    try:
        return skew_angle(ink_mask(document[index].render(scale=100 / 72).to_pil().convert("L")))
    finally:
        document.close()


def test_cleanup_removes_blank_pages_straightens_and_crops(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", [_scan(2.5), _scan(text=False, specks=400), _scan()])
    output = tmp_path / "limpo.pdf"

    result = CleanScannedPages().run(str(source), str(output))

    assert result.removed == [1]
    assert result.straightened == [0]
    assert result.cropped == [0, 2]
    reader = PdfReader(output)
    assert len(reader.pages) == 2
    assert float(reader.pages[0].cropbox.width) < 595 and float(reader.pages[0].cropbox.height) < 842
    assert _residual_skew(output, 0) == 0.0


def test_skew_on_a_rotated_page_is_measured_as_seen(tmp_path):
    # Escaneado de lado e posto de pé com /Rotate 90: a inclinação vale para a tela.
    sideways = _scan(-2.0).rotate(90, expand=True)
    source = _scan_pdf(tmp_path / "lado.pdf", [sideways], size=(842, 595))
    writer = PdfWriter(clone_from=str(source))
    writer.pages[0].rotate(90)
    writer.write(source)
    output = tmp_path / "limpo.pdf"

    result = CleanScannedPages().run(str(source), str(output), crop_margins=False)

    assert result.straightened == [0]
    assert _residual_skew(output, 0) == 0.0


def test_cleanup_refuses_to_remove_every_page(tmp_path):
    source = _scan_pdf(tmp_path / "vazio.pdf", [_scan(text=False), _scan(text=False)])
    with pytest.raises(ValueError, match="em branco"):
        CleanScannedPages().run(str(source), str(tmp_path / "limpo.pdf"))


@pytest.fixture
def page(tmp_path):
    if QApplication.instance() is None:
        QApplication([])
    session = DocumentSession()
    session.open(str(_scan_pdf(tmp_path / "scan.pdf", [_scan(), _scan(text=False)])))
    return ScanCleanupPage(session)


def test_cleaning_opens_an_undoable_version_and_reports_pages(page):
    original = page.session.path()
    page.deskew_check.setChecked(False)
    page.crop_check.setChecked(False)

    page.clean_button.click()
    wait_for_tasks()

    assert page.session.path() != original
    assert len(PdfReader(page.session.path()).pages) == 1
    assert "Páginas em branco removidas: 2." in page.status_label.text()
    page.session.undo()
    assert page.session.path() == original


def test_nothing_to_clean_keeps_the_document(page):
    original = page.session.path()
    page.blank_check.setChecked(False)
    page.crop_check.setChecked(False)

    page.clean_button.click()
    wait_for_tasks()

    assert page.session.path() == original
    assert page.status_label.text() == "Nenhuma página precisou de limpeza."
