"""Dica rica: abre 500 ms depois do mouse entrar ou na hora com o foco do teclado, no lugar da
dica do Qt, e cabe na janela do lado certo (à esquerda da coluna rápida, à direita das linhas
de ferramenta, abaixo da barra de marcação)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QFocusEvent, QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui import theme
from ui.main_window import MainWindow
from ui.tools_center import ToolRow
from ui.widgets.rich_tip import DELAY_MS, WIDTH, shown_tip


@pytest.fixture
def window(tmp_path, monkeypatch):
    theme.apply_theme(QApplication.instance() or QApplication([]), theme.LIGHT)
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    window.resize(1280, 720)
    window.show()
    QApplication.processEvents()
    yield window
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()


def _document(window, tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(str(tmp_path / "doc.pdf"))
    doc = window.open_document(str(tmp_path / "doc.pdf"))
    QApplication.processEvents()
    return doc


def _rect(widget, window) -> QRect:
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def test_hover_opens_after_the_delay_and_leaving_closes(window, tmp_path):
    doc = _document(window, tmp_path)
    button = doc._quick_buttons["CompressPage"]
    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    QTest.qWait(DELAY_MS // 2)
    assert shown_tip(window) is None  # ainda não: o mouse só passou
    QTest.qWait(DELAY_MS)
    tip = shown_tip(window)
    assert tip is not None and tip.title.text() == "Comprimir" and tip.width() == WIDTH
    assert tip.body.text().startswith("Diminua")
    # À esquerda da coluna rápida, que fica na borda direita, e dentro da janela.
    assert tip.geometry().right() < _rect(button, window).left()
    assert window.rect().contains(tip.geometry())
    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    assert shown_tip(window) is None


def test_leaving_before_the_delay_cancels_it(window, tmp_path):
    doc = _document(window, tmp_path)
    button = doc._quick_buttons["MergePage"]
    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    QTest.qWait(DELAY_MS + 100)
    assert shown_tip(window) is None


def test_keyboard_focus_opens_it_at_once_beside_the_tool_row(window):
    window.tabs.setCurrentWidget(window.tools_center)
    QApplication.processEvents()
    row = window.tools_center.findChildren(ToolRow)[0]
    QApplication.sendEvent(row, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    tip = shown_tip(window)
    assert tip is not None and tip.title.text() == row.name
    assert tip.geometry().left() > _rect(row, window).right()  # à direita da linha
    QApplication.sendEvent(row, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason))
    assert shown_tip(window) is None


def test_the_plain_qt_tooltip_is_swallowed(window, tmp_path):
    doc = _document(window, tmp_path)
    button = doc._quick_buttons["CompressPage"]
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(4, 4), button.mapToGlobal(QPoint(4, 4)))
    assert QApplication.sendEvent(button, event)  # tratado pelo filtro: o Qt não mostra a dele
    assert button.toolTip().startswith("<b>Comprimir")  # o texto continua lá, para quem lê


def test_markup_bar_tip_opens_below_with_the_key(window, tmp_path):
    doc = _document(window, tmp_path)
    window.open_tool_mode("AnnotationsPage")
    QApplication.processEvents()
    button = doc.markup_bar.button_for("highlight")
    QApplication.sendEvent(button, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    tip = shown_tip(window)
    assert tip is not None and tip.key.text() and tip.key.isVisibleTo(tip)
    assert tip.geometry().top() > _rect(button, window).bottom()
