"""Paleta de comandos e atalhos configuráveis (A18)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui import i18n
from ui.shortcuts import CommandPalette, ShortcutsDialog


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def make_window(settings):
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    windows = []

    def make():
        windows.append(MainWindow(settings=settings))
        return windows[-1]

    yield make
    for window in windows:
        window.close()


def _visible(palette):
    return [palette.list.item(row).text() for row in range(palette.list.count()) if not palette.list.item(row).isHidden()]


def test_palette_finds_tools_by_name_or_description_without_accents(make_window):
    window = make_window()
    palette = CommandPalette(window.commands(), window)
    palette.search.setText("comprim")  # também na descrição de Processar em lote
    assert _visible(palette) == ["Ferramentas › Comprimir", "Ferramentas › Processar em lote"]
    assert palette.list.currentItem().text() == "Ferramentas › Comprimir"
    palette.search.setText("CRIPTOGRAFICA")  # só na descrição da Assinatura digital
    assert _visible(palette) == ["Ferramentas › Assinatura digital"]
    palette.search.setText("pagina dupla")
    assert _visible(palette) == ["Páginas › Página dupla"]
    palette.search.setText("nada disso existe")
    assert _visible(palette) == [] and palette.list.currentRow() == -1


def test_palette_hides_disabled_commands_and_shows_shortcuts(make_window):
    window = make_window()
    texts = [palette_text for palette_text in _visible(CommandPalette(window.commands(), window))]
    assert not any("Salvar" in text for text in texts)  # sem documento aberto
    assert any(text.startswith("Arquivo › Abrir PDF...") and "Ctrl+O" in text for text in texts)


def test_palette_runs_the_chosen_command(make_window, monkeypatch):
    window = make_window()

    def fake_exec(palette):
        palette.search.setText("lote")
        QTest.keyClick(palette.search, Qt.Key.Key_Return)
        return palette.result()

    monkeypatch.setattr(CommandPalette, "exec", fake_exec)
    window._palette_action.trigger()
    assert window.stack.currentIndex() == window._row_of["BatchPage"]


def test_arrow_keys_in_the_search_move_through_the_list(make_window):
    window = make_window()
    palette = CommandPalette(window.commands(), window)
    palette.search.setText("verificar")
    assert palette.list.currentRow() >= 0
    first = palette.list.currentItem().text()
    QTest.keyClick(palette.search, Qt.Key.Key_Down)
    assert palette.list.currentItem().text() != first
    assert palette.list.currentItem().text() in _visible(palette)


def test_custom_shortcut_is_saved_and_survives_restart_and_language(make_window, monkeypatch):
    window = make_window()

    def fake_exec(dialog):
        dialog.editor("tool.CompressPage").setKeySequence(QKeySequence("Ctrl+Alt+C"))
        dialog.editor("file.print").clear()
        return 1

    monkeypatch.setattr(ShortcutsDialog, "exec", fake_exec)
    window.edit_shortcuts()
    tools = {action.objectName(): action for _label, action in window.commands()}
    assert tools["tool.CompressPage"].shortcut().toString() == "Ctrl+Alt+C"
    assert tools["file.print"].shortcut().isEmpty()

    i18n.set_language(i18n.EN_US)
    try:
        tools = {action.objectName(): action for _label, action in window.commands()}
        assert tools["tool.CompressPage"].shortcut().toString() == "Ctrl+Alt+C"
    finally:
        i18n.set_language(i18n.PT_BR)

    again = {action.objectName(): action for _label, action in make_window().commands()}
    assert again["tool.CompressPage"].shortcut().toString() == "Ctrl+Alt+C"
    assert again["file.print"].shortcut().isEmpty()
    assert [s.toString() for s in again["edit.redo"].shortcuts()] == ["Ctrl+Y", "Ctrl+Shift+Z"]


def test_restore_defaults_forgets_the_custom_shortcuts(make_window, settings):
    window = make_window()
    window._preferences.set_shortcut("file.open", "Ctrl+Alt+O")
    window._apply_shortcuts()
    dialog = ShortcutsDialog(window.commands(), window._default_shortcuts, window)
    assert dialog.editor("file.open").keySequence().toString() == "Ctrl+Alt+O"
    dialog.restore_defaults()
    changes = dialog.changes()
    assert set(changes.values()) == {None}
    assert dialog.editor("view.palette").keySequence().toString() == "Ctrl+K"
    window._preferences.set_shortcut("file.open", None)
    assert window._preferences.shortcut("file.open") is None
    assert settings.value("shortcuts/file.open") is None


def test_repeated_shortcuts_are_refused(make_window, monkeypatch):
    window = make_window()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text))
    dialog = ShortcutsDialog(window.commands(), window._default_shortcuts, window)
    assert dialog.conflict() is None

    dialog.editor("tool.MergePage").setKeySequence(QKeySequence("Ctrl+O"))
    assert "Abrir PDF" in dialog.conflict()
    dialog._accept()
    assert warnings and dialog.result() == 0

    dialog.editor("tool.MergePage").setKeySequence(QKeySequence("Ctrl+Shift+Z"))  # 2º atalho de Refazer
    assert "Refazer" in dialog.conflict()
    dialog.editor("tool.MergePage").setKeySequence(QKeySequence("Ctrl+F"))
    assert "visualizador" in dialog.conflict()
    dialog.editor("tool.MergePage").clear()
    dialog._accept()
    assert dialog.result() == 1
