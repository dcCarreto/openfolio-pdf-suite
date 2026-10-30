"""Etapa de refinamentos: animações (e nenhuma quando desligadas), F6 entre regiões, o painel
de tarefas, o aviso de atualização, os ícones e a acessibilidade dos botões."""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QAbstractAnimation, QSettings, QSize
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QMessageBox,
    QRadioButton,
)

from core import updates
from ui import motion, sidebar_icons, theme
from ui.main_window import MainWindow
from ui.preferences import preferences
from ui.shortcuts import CommandPalette
from ui.tasks import run_task, wait_for_tasks
from ui.tools import ROW_OF
from ui.update_dialog import UpdateDialog, edition_date, highlights
from ui.viewer import viewer_icons


@pytest.fixture
def window(tmp_path, monkeypatch):
    theme.apply_theme(QApplication.instance() or QApplication([]), theme.DARK)
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()


def _pdf(path, pages=3):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    writer.write(str(path))
    return str(path)


def _show(window, width, height):
    window.resize(width, height)
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    QApplication.processEvents()


def _exercise(window, tmp_path):
    """Tudo o que anima: painel, gaveta, barra de marcação, rodapé, paleta."""
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1440, 900)
    doc.open_tool(ROW_OF["CompressPage"])
    doc.panel(ROW_OF["CompressPage"]).task_started("Comprimindo")
    doc.panel(ROW_OF["CompressPage"]).task_finished("cancelled")
    doc.close_tool()
    doc.open_tool(ROW_OF["AnnotationsPage"])
    doc.annotation_state.set_tool("ink")
    _show(window, 1024, 720)
    doc.open_tool(ROW_OF["CompressPage"])
    CommandPalette(window.commands(), window).show()
    QTest.qWait(300)
    return doc


# -- animações ------------------------------------------------------------------------------


def test_with_animations_off_nothing_animates(window, tmp_path, monkeypatch):
    monkeypatch.setattr(motion, "enabled", lambda: preferences().animations())  # a preferência de verdade
    window._animations_action.setChecked(False)  # Exibir > Animações da interface
    started = []
    monkeypatch.setattr(QAbstractAnimation, "start", lambda self, *args: started.append(type(self).__name__))

    doc = _exercise(window, tmp_path)

    assert started == []
    assert doc.stack.isVisible() and doc.stack.width() > 0  # o estado final, sem animar


def test_animations_leave_no_effect_behind(window, tmp_path, monkeypatch):
    monkeypatch.setattr(motion, "enabled", lambda: True)
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1440, 900)
    doc.open_tool(ROW_OF["CompressPage"])
    panel = doc.panel(ROW_OF["CompressPage"])
    panel.task_started("Comprimindo")
    QTest.qWait(400)
    assert doc.stack.width() >= 300  # abriu até a largura do painel
    assert panel.footer.graphicsEffect() is None and doc.stack.graphicsEffect() is None

    doc.close_tool()
    assert doc.stack.isVisible()  # ainda encolhendo
    QTest.qWait(400)
    assert not doc.stack.isVisible()

    _show(window, 1024, 720)
    doc.open_tool(ROW_OF["CompressPage"])
    QTest.qWait(400)
    assert isinstance(doc.stack.graphicsEffect(), QGraphicsDropShadowEffect)  # a sombra volta na gaveta
    doc.open_tool(ROW_OF["AnnotationsPage"])
    QTest.qWait(400)
    assert isinstance(doc.markup_bar.graphicsEffect(), QGraphicsDropShadowEffect)


# -- F6 -----------------------------------------------------------------------------------


def test_f6_moves_between_regions(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    doc.open_tool(ROW_OF["CompressPage"])
    _show(window, 1440, 900)
    regions = window.regions()
    assert regions == [window.menuWidget(), doc.viewer.toolbar, doc.viewer.scroll_area, doc.stack, doc.right_rail]
    commands = {action.objectName(): action for _label, action in window.commands()}
    assert commands["view.next_region"].shortcut().toString() == "F6"

    visited = []
    for _ in regions:
        commands["view.next_region"].trigger()
        focus = QApplication.focusWidget()
        visited.append(next(r for r in regions if r is focus or r.isAncestorOf(focus)))
    assert sorted(map(id, visited)) == sorted(map(id, regions))  # passa por todas e volta
    commands["view.previous_region"].trigger()
    focus = QApplication.focusWidget()
    assert visited[-2] is focus or visited[-2].isAncestorOf(focus)


# -- tarefas ------------------------------------------------------------------------------


def test_the_tasks_button_and_popover(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1440, 900)
    release = threading.Event()
    try:
        run_task(doc.viewer, "Lenta", lambda progress: release.wait(5))
        QApplication.processEvents()
        assert window.tasks_button.isVisible() and window.tasks_button.text() == "1 tarefa em andamento"
        window.tasks_button.click()
        popover = window.tasks_button.popover
        assert popover.isVisible() and popover.rows.count() == 1
        assert popover.geometry().bottom() < window.tasks_button.mapToGlobal(window.tasks_button.rect().topLeft()).y()
    finally:
        release.set()
    assert wait_for_tasks()
    assert window.tasks_button.text() == "1 concluída"
    assert [entry.state for entry in window.task_log.entries] == ["ok"]
    popover.clear_button.click()
    assert window.task_log.entries == []
    assert not window.tasks_button.isVisible()  # só aparece quando há tarefas


def test_each_task_row_says_how_it_ended(window, tmp_path, monkeypatch):
    from ui.widgets import task_popover

    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1440, 900)
    release = threading.Event()
    try:
        run_task(doc.viewer, "Lenta", lambda progress: release.wait(5))
        QApplication.processEvents()
        window.tasks_button.click()
        popover = window.tasks_button.popover
        row = popover.rows.itemAt(0).widget()
        assert row.action.text() == "Cancelar" and popover.width() == 380
        corner = window.mapToGlobal(window.rect().bottomRight())
        # 8 px da direita e 32 de baixo da janela (com folga para a moldura de cada sistema)
        assert abs(corner.x() - popover.geometry().right() - 8) <= 4
        assert abs(corner.y() - popover.geometry().bottom() - 32) <= 4
    finally:
        release.set()
    assert wait_for_tasks()

    monkeypatch.setattr("ui.tasks.show_error", lambda *args, **kwargs: None)

    def fail(_progress):
        raise ValueError("O arquivo pede senha.")

    run_task(doc.viewer, "Comprimir", fail)
    assert wait_for_tasks()
    QApplication.processEvents()
    failed, done = (popover.rows.itemAt(n).widget() for n in range(2))
    assert failed.entry.state == task_popover.FAILED and "O arquivo pede senha." in failed.detail.text()
    assert failed.action.text() == "Ver motivo"
    assert done.action.text() == "Ver" and "agora" in done.detail.text()
    window.tabs.setCurrentWidget(window.home)
    done.action.click()  # Ver: a aba do documento em que ela rodou
    assert window.tabs.currentWidget() is doc
    assert task_popover.ago(1000, now=1000 + 150) == "há 2 min"


# -- aviso de atualização -----------------------------------------------------------------------


def test_update_dialog_dates_news_and_consent(window, monkeypatch):
    update = updates.Update(
        page=updates.RELEASES_PAGE,
        notes="## Visual\n\n" + "\n".join(f"- Item {n}" for n in range(1, 8)),
        version="v2026.10.22",
    )
    opened = []
    monkeypatch.setattr("ui.update_dialog.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    dialog = UpdateDialog(update, can_install=True, parent=window, current="2026.9.3")

    assert dialog.when_label.text() == "Edição de 22 de outubro de 2026. Você usa a de 3 de setembro de 2026."
    assert dialog.notes.toPlainText().count("Item") == 5  # até 5 novidades
    assert dialog.accept_button.isDefault() and dialog.accept_button.text() == "Baixar e instalar"

    dialog.notes_button.click()  # ver as notas não aceita nada
    assert opened == [updates.RELEASES_PAGE] and dialog.result() == 0
    dialog.later_button.click()
    assert dialog.result() == 0  # Agora não

    before = preferences().check_updates_on_start()
    dialog.notify_box.setChecked(not before)
    assert preferences().check_updates_on_start() is (not before)
    dialog.notify_box.setChecked(before)


def test_edition_dates_and_highlights():
    assert edition_date("v2026.10.22") == "22 de outubro de 2026"
    assert edition_date("0.0.0+dev") == ""
    assert highlights("- a\n  continua\n- b") == "- a continua\n- b"
    assert highlights("Sem lista.") == "Sem lista."


# -- ícones e acessibilidade ----------------------------------------------------------------


def _builders():
    found = [getattr(sidebar_icons, n) for n in dir(sidebar_icons) if n.startswith("build_")]
    found += [getattr(viewer_icons, n) for n in dir(viewer_icons) if n.startswith("build_") and n != "build_markup_icon"]
    return found


@pytest.mark.parametrize("key", [theme.DARK, theme.LIGHT])
def test_every_icon_draws_in_both_themes(key):
    theme.apply_theme(QApplication.instance() or QApplication([]), key)
    for build in _builders():
        image = build().pixmap(QSize(18, 18)).toImage()
        assert any(image.pixelColor(x, y).alpha() for x in range(18) for y in range(18)), build.__name__
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected, QIcon.Mode.Disabled):
        assert not viewer_icons.build_file_icon().pixmap(QSize(18, 18), mode).isNull()


def _visible_buttons(window):
    for button in window.findChildren(QAbstractButton):
        if button.isVisible() and not isinstance(button.parentWidget(), QLineEdit):  # a lupa do campo
            yield button


def test_click_areas_and_names_of_icon_buttons(window, tmp_path):
    states = []
    _show(window, 1440, 900)
    states.append(list(_visible_buttons(window)))
    window.tabs.setCurrentIndex(1)
    states.append(list(_visible_buttons(window)))
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    for class_name in ("CompressPage", "AnnotationsPage", "OrganizePage"):
        doc.open_tool(ROW_OF[class_name])
        QApplication.processEvents()
        states.append(list(_visible_buttons(window)))
    _show(window, 1024, 720)
    states.append(list(_visible_buttons(window)))

    for buttons in states:
        for button in buttons:
            label = button.accessibleName() or button.text() or button.toolTip()
            if not isinstance(button, (QCheckBox, QRadioButton)):
                assert button.width() >= 28 and button.height() >= 28, (label, button.size())
            if not button.text() and not button.icon().isNull():
                assert button.accessibleName(), button.toolTip()  # só ícone: o leitor de tela lê o nome


def test_the_side_panel_header_names_what_it_shows(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf", pages=4))
    _show(window, 1600, 900)
    assert doc.side_title.text() == "Miniaturas" and doc.side_count.text() == "4"
    doc.viewer.show_side_panel(False)
    assert not doc.side_container.isVisible()
    doc.viewer.show_side_panel(True)
    assert doc.side_container.isVisible()


def test_rail_tooltips_show_a_configured_shortcut(window, tmp_path, monkeypatch):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    window._preferences.set_shortcut("tool.CompressPage", "Ctrl+Alt+C")
    window._apply_shortcuts()
    shown = QKeySequence("Ctrl+Alt+C").toString(QKeySequence.SequenceFormat.NativeText)  # "⌥⌘C" no macOS
    # A dica rica: o nome com o atalho, em negrito, e uma frase sobre o efeito.
    assert doc._quick_buttons["CompressPage"].toolTip().startswith(f"<b>Comprimir ({shown})</b><br>Diminua")
    assert doc._quick_buttons["MergePage"].toolTip().startswith("<b>Mesclar</b><br>")
    assert doc._quick_buttons["CompressPage"].text() == "Comprimir"  # o rótulo embaixo do ícone
