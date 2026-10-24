"""O painel de ferramenta: Entrada, Opções, Saída e o rodapé com os estados."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QMessageBox, QWidget

from ui import tool_panel
from ui.main_window import MainWindow
from ui.tasks import wait_for_tasks
from ui.tools import SECTIONS
from ui.widgets.file_picker import FilePicker


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()


def _pdf(path, pages=2):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    writer.write(str(path))
    return str(path)


_WITHOUT_OPTIONS = {"ExtractTextPage", "ExtractImagesPage"}  # só entrada e saída


def _section_titles(panel) -> list[str]:
    labels = panel.body.findChildren(QLabel)
    return [label.text() for label in labels if label.property("ofRole") == "section" and label.isVisibleTo(panel)]


@pytest.mark.parametrize("row", range(len(SECTIONS)), ids=[section[4] for section in SECTIONS])
def test_every_tool_follows_the_panel_pattern(window, tmp_path, row):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    page = doc.open_tool(row)
    panel = doc.panel(row)

    expected = ["ENTRADA"] if hasattr(page, "source_bar") else []
    expected += [] if SECTIONS[row][4] in _WITHOUT_OPTIONS else ["OPÇÕES"]
    expected += ["SAÍDA"] if hasattr(page, "output_picker") else []
    assert _section_titles(panel) == expected
    assert panel.title_label.text() == SECTIONS[row][1] and panel.close_button.isVisibleTo(panel)
    if getattr(page, "action_buttons", []):
        action = panel.current_action()
        assert panel.primary_button.isVisibleTo(panel) and panel.primary_button.text() == action.text()
        assert not action.isVisibleTo(page)  # o rodapé faz o papel dele
    assert panel.state() == tool_panel.READY


@pytest.mark.parametrize("row", range(len(SECTIONS)), ids=[section[4] for section in SECTIONS])
def test_no_option_is_lost_in_the_panel(window, row):
    doc = window.current_document()
    page = doc._page_content(row)
    kinds = (QLineEdit, QComboBox, FilePicker)
    before = [w for w in page.findChildren(QWidget) if isinstance(w, kinds)]
    before += [w for w in (getattr(page, "source_bar", None), getattr(page, "output_picker", None)) if w is not None]

    panel = tool_panel.ToolPanel(QIcon(), "t", "d", page, doc.session, doc.tasks)

    assert all(panel.isAncestorOf(widget) for widget in before)


def test_mode_switch_changes_the_footer_action(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    page = doc.open_tool(window._row_of["PDFAPage"])
    panel = doc.panel(window._row_of["PDFAPage"])
    assert panel.primary_button.text() == "Converter"

    page.mode_combo.setCurrentIndex(1)
    assert panel.primary_button.text() == "Validar"


def test_compress_goes_ready_busy_success_and_undo_names_the_tool(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf", pages=3))
    row = window._row_of["CompressPage"]
    doc.open_tool(row)
    panel = doc.panel(row)
    states = []
    doc.tasks.started.connect(lambda _title: states.append(panel.state()))

    assert window._run_tool_action.shortcuts()[0].toString() == "Ctrl+Return"
    window._run_tool_action.trigger()  # Ctrl+Enter
    assert wait_for_tasks()

    assert states == [tool_panel.BUSY]
    assert panel.state() in (tool_panel.SUCCESS, tool_panel.INFO)
    assert panel.result_card.title.text()
    assert window.statusBar().currentMessage()
    if panel.state() == tool_panel.SUCCESS:
        assert window._undo_action.text() == "Desfazer Comprimir"
        panel.undo_button.click()
        assert not doc.session.can_undo()
    panel.result_button.click()  # Concluir
    assert panel.state() == tool_panel.READY


def test_a_failure_shows_the_error_card_and_try_again(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    row = window._row_of["ExtractTextPage"]
    page = doc.open_tool(row)
    panel = doc.panel(row)
    page.output_picker._path = str(tmp_path / "nao_existe" / "texto.txt")  # a pasta não existe

    panel.run()
    assert wait_for_tasks()

    assert panel.state() == tool_panel.ERROR and not shown  # no painel, não num diálogo
    assert panel.result_button.text() == "Tentar de novo"
    card = panel.result_card
    assert card.technical.text() and not card.technical.isVisibleTo(card)  # o texto técnico fica recolhido
    assert window.statusBar().currentMessage() == card.title.text()
    card.technical_button.click()
    assert card.technical.isVisibleTo(card)


def test_a_missing_choice_is_an_error_in_the_panel_not_a_dialog(window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail("diálogo"))
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    row = window._row_of["WatermarkPage"]
    page = doc.open_tool(row)
    page.text_edit.setText("")

    doc.panel(row).run()

    assert doc.panel(row).state() == tool_panel.ERROR


def test_busy_footer_cancels_and_reports_it(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    row = window._row_of["CompressPage"]
    doc.open_tool(row)
    panel = doc.panel(row)
    cancelled = []
    doc.tasks.cancel = lambda: cancelled.append(True)

    panel.task_started("Comprimindo")
    assert panel.state() == tool_panel.BUSY and not panel.body.isEnabled()
    panel.task_progress(2, 4, "")
    assert panel.busy_percent.text() == "50%"
    panel.cancel_button.click()
    assert cancelled
    panel.task_finished("cancelled")
    assert panel.state() == tool_panel.INFO and panel.body.isEnabled()


def test_without_a_document_the_tool_waits_for_one(window, tmp_path):
    row = window._row_of["CompressPage"]
    window.open_tool(row)
    doc = window.document
    panel = doc.panel(row)

    assert window.tabs.tabText(window.tabs.indexOf(doc)) == "Comprimir"
    assert panel.state() == tool_panel.EMPTY and not panel.primary_button.isEnabled()
    assert panel.empty_caption.isVisibleTo(panel)
    assert not doc._quick_buttons[row].isEnabled() and not doc.viewer.page_field.isEnabled()

    page = doc.page(row)
    page.level_combo.setCurrentIndex(2)
    assert window.open_document(_pdf(tmp_path / "doc.pdf")) is doc

    assert panel.state() == tool_panel.READY and panel.primary_button.isEnabled()
    assert page.level_combo.currentIndex() == 2  # as opções escolhidas antes ficam
    assert window.tabs.tabText(window.tabs.indexOf(doc)) == "doc.pdf"


def test_in_a_narrow_window_the_panel_is_a_drawer(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    window.resize(1024, 720)
    window.show()
    QApplication.processEvents()
    row = window._row_of["CompressPage"]

    doc._quick_buttons[row].click()
    QApplication.processEvents()
    assert doc.is_drawer_open() and doc.stack.parentWidget() is doc
    assert doc.stack.geometry().right() < doc.right_rail.mapTo(doc, doc.right_rail.rect().topLeft()).x()

    QTest.keyClick(doc, Qt.Key.Key_Escape)
    assert not doc.is_drawer_open() and doc.current_tool() == row  # a ferramenta segue aberta
    doc._quick_buttons[row].click()
    assert doc.is_drawer_open()

    window.resize(1440, 900)
    QApplication.processEvents()
    assert not doc._drawer and doc.splitter.widget(2) is doc.stack and doc.stack.isVisible()


def test_escape_closes_the_tool(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    window.resize(1440, 900)  # larga: sem a gaveta, Esc fecha a ferramenta
    window.show()
    doc.open_tool(window._row_of["CompressPage"])

    QTest.keyClick(doc, Qt.Key.Key_Escape)

    assert doc.current_tool() == -1


def test_outside_a_panel_messages_still_use_dialogs(monkeypatch):
    QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))
    tool_panel.notify_success(QWidget(), "Título", "Feito.")
    assert shown == ["Feito."]
