"""Testes de ui/properties_dialog.py e de Arquivo > Propriedades do documento (A12)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel
from reportlab.pdfgen import canvas as rl_canvas

from ui import i18n
from ui.main_window import MainWindow
from ui.properties_dialog import describe_page_size, format_file_size
from ui.tasks import wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_sizes_are_written_for_people():
    assert format_file_size(512) == "512 bytes"
    assert format_file_size(1_234_567) == "1,2 MB (1.234.567 bytes)"
    assert describe_page_size(595.28, 841.89) == "210 × 297 mm (A4, retrato)"
    assert describe_page_size(792, 612) == "279 × 216 mm (Carta (Letter), paisagem)"
    assert describe_page_size(300, 300) == "106 × 106 mm"
    i18n.set_language(i18n.EN_US)
    try:
        assert format_file_size(1_234_567) == "1.2 MB (1,234,567 bytes)"
        assert describe_page_size(595.28, 841.89) == "210 × 297 mm (A4, portrait)"
    finally:
        i18n.set_language(i18n.PT_BR)


def test_file_menu_opens_the_properties_of_the_working_document(tmp_path):
    _app()
    path = tmp_path / "relatorio.pdf"
    canvas = rl_canvas.Canvas(str(path), pagesize=(595.28, 841.89))
    canvas.setFont("Helvetica", 12)
    canvas.drawString(40, 800, "texto")
    canvas.showPage()
    canvas.save()
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert not window._properties_action.isEnabled()
    window.session.open(str(path))
    assert window._properties_action.isEnabled()

    assert window.show_document_properties()
    wait_for_tasks()
    QApplication.processEvents()

    dialog = window._properties_dialog
    assert dialog.isVisible()
    general = [label.text() for label in dialog.tabs.widget(0).findChildren(QLabel)]
    assert "relatorio.pdf" in general and "1" in general
    font = dialog.fonts_tree.topLevelItem(0)
    assert [font.text(c) for c in (0, 2, 4)] == ["Helvetica", "Não (fonte padrão)", "1"]
    assert dialog.pages_tree.topLevelItem(0).text(0) == "210 × 297 mm (A4, retrato)"
    dialog.close()
    window.session.clear()
