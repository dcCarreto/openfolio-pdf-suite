"""As abas Início e Ferramentas e a paleta de comandos (Ctrl+K)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui import home_page, theme
from ui.main_window import MainWindow
from ui.shortcuts import GROUPS, MAX_PER_GROUP, CommandPalette, command_group
from ui.tools import ROW_OF, SECTIONS
from ui.tools_center import columns_for


@pytest.fixture
def window(tmp_path, monkeypatch):
    theme.apply_theme(QApplication.instance() or QApplication([]), theme.DARK)
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


def _show(window, width, height):
    window.resize(width, height)
    window.show()
    QApplication.processEvents()


# -- Início -----------------------------------------------------------------------------


def _mime(*paths) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
    return mime


def test_dropping_a_pdf_anywhere_on_home_opens_it(window, tmp_path):
    path = _pdf(tmp_path / "solto.pdf")
    home = window.home
    mime = _mime(path)
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    home.dragEnterEvent(enter)
    assert enter.isAccepted() and home.drop_zone.property("dragOver") is True

    drop = QDropEvent(QPointF(900, 600), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    home.dropEvent(drop)
    assert window.document is not None and window.document.session.source_path() == path
    assert home.drop_zone.property("dragOver") is False


def test_a_file_that_is_not_a_pdf_is_not_taken(window, tmp_path):
    text = tmp_path / "nota.txt"
    text.write_text("x")
    mime = _mime(str(text))  # o evento não guarda o QMimeData: precisa viver até o fim
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.home.dragEnterEvent(enter)
    assert not enter.isAccepted()


def test_home_has_the_four_starters_and_opens_them(window):
    names = [card.text() for card in window.home.starter_cards]
    assert names == ["Criar PDF", "Mesclar", "Converter", "Comprimir"]
    window.home.starter_cards[1].click()
    assert window.document.current_tool() == ROW_OF["MergePage"]


def test_recent_files_show_thumbnail_pages_and_a_menu(window, tmp_path):
    first, second = _pdf(tmp_path / "um.pdf", 3), _pdf(tmp_path / "dois.pdf")
    window._preferences.add_recent_file(first)
    window._preferences.add_recent_file(second)
    window.home.refresh()
    recent = window.home.recent_list
    assert [recent.item(row).text() for row in range(recent.count())] == ["dois.pdf", "um.pdf"]

    pixmap, pages = home_page.recent_info(first)
    assert pixmap is not None and not pixmap.isNull() and pages == 3
    assert home_page.recent_info(first)[0] is pixmap  # do cache: o arquivo não é aberto de novo

    window.home.remove_recent(second)  # "Remover da lista"
    assert [recent.item(row).text() for row in range(recent.count())] == ["um.pdf"]
    window.home._clear_button.click()  # "Limpar lista"
    assert recent.count() == 0 and window.home._empty_label.isVisibleTo(window.home)
    assert not window._recent_menu.isEnabled()


def test_relative_dates():
    now = 1_700_000_000.0
    assert home_page.relative_date(now - 60, now).startswith("hoje")
    assert home_page.relative_date(now - 86400, now) == "ontem"
    assert home_page.relative_date(now - 3 * 86400, now) == "há 3 dias"
    assert home_page.relative_date(now - 30 * 86400, now).count("/") == 2


# -- Ferramentas ------------------------------------------------------------------------


def _visible_names(tools) -> list[str]:
    return [card.text() for card in tools.visible_cards()]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("cpf", ["Redigir/Sanitizar"]),
        ("assinar", ["Preencher e assinar", "Assinatura digital"]),
        ("word", ["Converter"]),
        ("COMPRIMIR", ["Comprimir", "Processar em lote"]),  # sem diferença de maiúsculas
    ],
)
def test_the_tools_search_knows_synonyms(window, query, expected):
    tools = window.tools_center
    tools.search.setText(query)
    assert _visible_names(tools) == expected


def test_category_chips_filter_and_count(window):
    tools = window.tools_center
    assert tools.chips[0].text().endswith(str(len(SECTIONS))) and tools.chips[0].isChecked()
    tools.chips[3].click()  # Formulários e assinatura
    assert _visible_names(tools) == ["Campos de formulário", "Assinatura digital"]
    tools.chips[0].click()
    assert len(tools.visible_cards()) == len(SECTIONS)


def test_the_grid_goes_from_4_to_3_columns_below_about_1100(window):
    window.tabs.setCurrentWidget(window.tools_center)
    _show(window, 1280, 800)
    assert window.tools_center.columns() == 4
    _show(window, 1080, 720)
    assert window.tools_center.columns() == 3
    assert columns_for(1160) == 4 and columns_for(1000) == 3


def test_enter_opens_the_first_result_and_arrows_move_between_cards(window):
    window.tabs.setCurrentWidget(window.tools_center)
    _show(window, 1440, 900)
    tools = window.tools_center
    tools.search.setText("assinar")
    QTest.keyClick(tools.search, Qt.Key.Key_Return)
    assert window.document.current_tool() == ROW_OF["FillSignPage"]

    window.tabs.setCurrentWidget(window.tools_center)
    tools.search.clear()
    first = tools.visible_cards()[0]
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Right)
    assert QApplication.focusWidget() is tools.visible_cards()[1]
    QTest.keyClick(tools.visible_cards()[1], Qt.Key.Key_Down)
    assert QApplication.focusWidget() is tools.visible_cards()[1 + tools.columns()]


def test_quick_rail_tools_have_a_pin(window):
    cards = window.tools_center.cards
    assert cards[ROW_OF["CompressPage"]].pinned and not cards[ROW_OF["SplitPage"]].pinned


# -- Paleta -----------------------------------------------------------------------------


def _visible_rows(palette):
    return [row for row in range(palette.list.count()) if not palette.list.item(row).isHidden()]


def test_the_palette_finds_every_command_it_found_before(window):
    commands = [c for c in window.commands() if c[1].isEnabled()]
    palette = CommandPalette(window.commands(), window)
    for label, action in commands:  # cada comando habilitado acha a si mesmo pelo rótulo
        palette.search.setText(label)
        found = [palette._actions[row] for row in _visible_rows(palette)]
        assert action in found, label
    assert sorted(id(a) for a in palette._actions) == sorted(id(a) for _l, a in commands)


def test_the_palette_groups_and_limits_each_group(window):
    palette = CommandPalette(window.commands(), window)
    rows = _visible_rows(palette)
    groups = [palette.list.item(row).data(Qt.ItemDataRole.UserRole + 3) for row in rows]
    order = [key for key, _title in GROUPS]
    assert groups == sorted(groups, key=order.index)  # Ferramentas, Exibir, Navegar, Recentes, Ações
    assert groups.count("tools") == MAX_PER_GROUP
    headers = [row for row in rows if palette.list.item(row).data(Qt.ItemDataRole.UserRole + 4)]
    assert len(headers) == len(set(groups))  # um título por grupo

    QTest.keyClick(palette.search, Qt.Key.Key_Tab)  # Tab: só Ferramentas, todas
    assert palette.category_label.text() == "Ferramentas"
    assert len(_visible_rows(palette)) == len(SECTIONS)
    assert command_group(palette._actions[_visible_rows(palette)[0]]) == "tools"


def test_the_palette_offers_open_documents_and_recent_files(window, tmp_path):
    path = _pdf(tmp_path / "contrato.pdf")
    window.open_document(path)
    palette = CommandPalette(window.commands(), window, extras=window._palette_extras())
    palette.search.setText("contrato")
    groups = {palette.list.item(row).data(Qt.ItemDataRole.UserRole + 3) for row in _visible_rows(palette)}
    assert groups == {"navigate", "recent"}

    window.tabs.setCurrentWidget(window.home)
    palette.set_category("navigate")
    palette._run()
    palette.chosen.trigger()
    assert window.tabs.currentWidget() is window.document


def test_clicking_outside_the_palette_closes_it(window):
    _show(window, 1280, 800)
    palette = CommandPalette(window.commands(), window)
    palette.show()
    QTest.qWait(250)  # a entrada animada (y de 80 a 88) termina
    assert palette.frame.geometry().top() == 88 and palette.frame.width() == 640
    QTest.mouseClick(palette, Qt.MouseButton.LeftButton, pos=QPoint(10, palette.height() - 10))
    assert not palette.isVisible()
