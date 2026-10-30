"""As abas Início e Ferramentas e a paleta de comandos (Ctrl+K)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton

from ui import home_page, i18n, search_index, theme, tools_center
from ui.main_window import MainWindow
from ui.shortcuts import GROUPS, MAX_PER_GROUP, CommandPalette, command_group
from ui.tools import DEFAULT_QUICK, GROUPS as TOOL_GROUPS, ROW_OF, TOOLS
from ui.tools_center import COLUMNS


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


def test_home_starters_open_the_tool_for_what_you_want_to_do(window):
    names = [button.text() for button in window.home.starter_buttons]
    assert names == [
        "Juntar PDFs", "Diminuir o tamanho", "Assinar", "Transformar em Word",
        "Esconder dados pessoais", "Tornar pesquisável",
    ]  # fmt: skip
    window.home.starter_buttons[0].click()
    assert window.document.current_tool_id() == "MergePage"
    window.tabs.setCurrentWidget(window.home)
    window.home.starter_buttons[3].click()  # Converter › Do PDF para…, que começa no Word
    assert (window.document.current_tool_id(), window.document.current_mode()) == ("ConvertPage", 0)
    assert "Word" in window.document.pages()[ROW_OF["ConvertPage"]].direction_combo.currentText()


def test_the_drop_zone_shrinks_to_a_strip_when_there_are_recent_files(window, tmp_path):
    assert window.home.drop_zone.height() == 240
    window._preferences.add_recent_file(_pdf(tmp_path / "um.pdf"))
    window.home.refresh()
    assert window.home.drop_zone.height() == 96


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
    return [row.text() for row in tools.visible_cards()]


def test_the_tools_tab_has_23_tools_in_8_groups_on_a_4_by_2_grid(window):
    tools = window.tools_center
    assert len(TOOLS) == 23 and len(tools.groups) == 8 == len(TOOL_GROUPS)
    assert len(tools.visible_cards()) == 23
    assert [card.name for card in tools.groups[:4]] == [
        "Montar e organizar", "Editar o conteúdo", "Revisar e comentar", "Preencher e assinar",
    ]  # fmt: skip
    grid = tools.groups[0].parentWidget().layout().itemAt(2).layout()
    positions = [grid.getItemPosition(grid.indexOf(card))[:2] for card in tools.groups]
    assert positions == [(row, column) for row in range(2) for column in range(COLUMNS)]


def test_every_tool_fits_without_scrolling_at_1280_by_720(window):
    window.tabs.setCurrentWidget(window.tools_center)
    _show(window, 1280, 720)
    tools = window.tools_center
    assert tools.verticalScrollBar().maximum() == 0
    viewport = tools.viewport().rect()
    for row in tools.visible_cards():
        top_left = row.mapTo(tools.viewport(), QPoint(0, 0))
        assert viewport.contains(top_left) and viewport.contains(top_left + QPoint(row.width() - 1, row.height() - 1))


@pytest.mark.parametrize(
    ("query", "expected", "reason"),
    [
        ("cpf", ["Redigir e limpar"], "cpf"),
        ("word", ["Converter"], ""),  # está na descrição: não precisa de motivo
        ("docx", ["Converter"], "docx"),
        ("assinatura digital", ["Preencher e assinar"], "assinatura"),  # o nome antigo
        ("extrair texto", ["Converter"], "extrair"),  # um modo
        ("COMPRIMIR", ["Comprimir"], ""),  # sem diferença de maiúsculas
    ],
)
def test_the_tools_search_filters_the_cards_in_place(window, query, expected, reason):
    tools = window.tools_center
    tools.search.setText(query)
    assert _visible_names(tools) == expected
    row = tools.visible_cards()[0]
    assert row.reason.text() == (f"por “{reason}”" if reason else "")
    assert sum(not card.isHidden() for card in tools.groups) == 1  # os grupos vazios somem


def test_only_one_search_field_is_visible_at_a_time(window):
    _show(window, 1280, 720)
    assert window._command_launcher.isVisible()
    window.tabs.setCurrentWidget(window.tools_center)
    assert not window._command_launcher.isVisible()
    window.show_command_palette()  # Ctrl+K nesta aba vai para o campo grande
    assert QApplication.focusWidget() is window.tools_center.search
    window.tabs.setCurrentWidget(window.home)
    assert window._command_launcher.isVisible()


def test_enter_opens_the_first_result_and_arrows_move_between_rows(window):
    window.tabs.setCurrentWidget(window.tools_center)
    _show(window, 1440, 900)
    tools = window.tools_center
    tools.search.setText("assinar")
    QTest.keyClick(tools.search, Qt.Key.Key_Return)
    assert window.document.current_tool_id() == "FillSignPage"

    window.tabs.setCurrentWidget(window.tools_center)
    tools.search.clear()
    first = tools.visible_cards()[0]
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Down)
    assert QApplication.focusWidget() is tools.visible_cards()[1]
    QTest.keyClick(tools.visible_cards()[1], Qt.Key.Key_Up)
    assert QApplication.focusWidget() is first


def test_every_name_of_the_tools_tab_has_an_english_version():
    texts = {home_page_label for home_page_label, *_ in home_page.STARTERS} | {tools_center._AUTOMATE_NOTE}
    for tool in TOOLS.values():
        texts |= {tool.title, tool.description, *(mode.label for mode in tool.modes)} | ({tool.short} - {""})
    for name, phrase, _ids in TOOL_GROUPS:
        texts |= {name, phrase}
    assert sorted(text for text in texts if text not in i18n._EN_TRANSLATIONS) == []


def test_an_ampersand_in_a_name_is_shown_not_taken_as_a_shortcut(window, monkeypatch):
    monkeypatch.setattr(i18n, "_current_language", i18n.EN_US)
    window.tools_center.retranslate()
    row = window.tools_center.cards["FillSignPage"]
    assert row.text() == "Fill & sign" and "&&" in QToolButton.text(row)
    assert any(pill.text() == "Fill && sign" for pill in window.tools_center.favorites)
    window.tabs.setTabText(0, "A&B.pdf")
    assert window.tabs.tabText(0) == "A&B.pdf" and window.tabs.tabBar().tabText(0) == "A&&B.pdf"


def test_a_long_tool_name_is_elided_before_the_pin(window):
    window.tabs.setCurrentWidget(window.tools_center)
    _show(window, 1000, 640)
    row = window.tools_center.cards["ProtectPage"]
    row.resize(150, row.height())
    shown = QToolButton.text(row)
    assert shown.endswith("…") and row.fontMetrics().horizontalAdvance(shown) < row.pin.geometry().left()


def test_the_most_used_follow_real_use(window):
    names = [pill.text() for pill in window.tools_center.favorites]
    assert names == ["Comprimir", "Mesclar", "Preencher e assinar", "Converter", "Organizar páginas"]
    for _ in range(2):
        window.open_tool_mode("SplitPage")
        window.document.close_tool()
    window.tools_center.retranslate()
    assert window.tools_center.favorites[0].text() == "Dividir"


def test_pinning_a_tool_puts_it_in_every_quick_rail(window, tmp_path):
    tools = window.tools_center
    assert tools.cards["CompressPage"].pin.isVisibleTo(tools.cards["CompressPage"])
    assert not tools.cards["SplitPage"].pin.isVisibleTo(tools.cards["SplitPage"])
    doc = window.open_document(_pdf(tmp_path / "a.pdf"))
    assert list(doc._quick_buttons) == DEFAULT_QUICK

    window.set_quick_tools([*DEFAULT_QUICK, "SplitPage"])  # "Fixar na coluna rápida"
    assert list(doc._quick_buttons)[-1] == "SplitPage"
    assert tools.cards["SplitPage"].pin.isVisibleTo(tools.cards["SplitPage"])
    assert window._preferences.quick_tools()[-1] == "SplitPage"  # fica nas configurações

    doc.quick_tools_changed.emit([t for t in window._preferences.quick_tools() if t != "OCRPage"])  # "Remover da coluna"
    assert "OCRPage" not in doc._quick_buttons and not tools.cards["OCRPage"].pin.isVisibleTo(tools.cards["OCRPage"])


def test_the_quick_rail_has_labels_and_goes_compact_below_1100(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "a.pdf"))
    _show(window, 1280, 720)
    button = doc._quick_buttons["AnnotationsPage"]
    assert doc.right_rail.width() == 68 and button.text() == "Anotar"
    assert doc.all_tools_button.text() == "Todas"
    _show(window, 1040, 700)
    assert doc.right_rail.width() == 48 and button.text() == "" and button.size().width() == 36
    assert button.accessibleName() == "Anotações"


# -- Paleta -----------------------------------------------------------------------------


def _visible_rows(palette):
    return [row for row in range(palette.list.count()) if not palette.list.item(row).isHidden()]


def _names(palette):
    return [palette.list.item(row).data(Qt.ItemDataRole.UserRole) for row in _visible_rows(palette)]


def test_the_palette_finds_every_command_it_found_before(window):
    commands = [c for c in window.commands() if c[1].isEnabled()]
    palette = CommandPalette(window.commands(), window)
    for label, action in commands:  # cada comando habilitado acha a si mesmo pelo rótulo
        palette.search.setText(label)
        found = [palette._actions[row] for row in _visible_rows(palette)]
        assert action in found, label
    assert sorted(id(a) for a in palette._actions) == sorted(id(a) for _l, a in commands)


def test_the_palette_groups_tools_and_commands(window):
    palette = CommandPalette(window.commands(), window)
    rows = _visible_rows(palette)
    groups = [palette.list.item(row).data(Qt.ItemDataRole.UserRole + 3) for row in rows]
    order = [key for key, _title in GROUPS]
    assert order == ["tools", "commands"]
    assert groups == sorted(groups, key=order.index)
    assert groups.count("tools") == MAX_PER_GROUP
    headers = [row for row in rows if palette.list.item(row).data(Qt.ItemDataRole.UserRole + 4)]
    assert len(headers) == len(set(groups))  # um título por grupo


def test_the_palette_shows_modes_and_why_a_synonym_matched(window):
    palette = CommandPalette(window.commands(), window)
    palette.search.setText("certificado")
    assert "Preencher e assinar › Certificado digital" in _names(palette)

    palette.search.setText("cpf")
    first = palette.list.item(_visible_rows(palette)[0])
    assert first.data(Qt.ItemDataRole.UserRole) == "Redigir e limpar"
    assert first.data(Qt.ItemDataRole.UserRole + 5) == "cpf"

    palette.search.setText("preencher")
    QTest.keyClick(palette.search, Qt.Key.Key_Tab)  # Tab: os modos da ferramenta destacada
    assert palette.category_label.text() == "Preencher e assinar"
    assert len(_visible_rows(palette)) == len(TOOLS["FillSignPage"].modes)
    QTest.keyClick(palette.search, Qt.Key.Key_Backtab)
    assert not palette.category_label.isVisibleTo(palette)


def test_the_palette_opens_a_mode(window):
    palette = CommandPalette(window.commands(), window)
    palette.search.setText("certificado digital")
    palette._run()
    palette.chosen.trigger()
    assert (window.document.current_tool_id(), window.document.current_mode()) == ("FillSignPage", 2)


def test_old_tool_ids_still_work_as_commands(window):
    action = next(a for _label, a in window.commands() if a.objectName() == "tool.ExtractTextPage")
    action.trigger()  # Extrair texto virou Converter › Extrair texto
    assert (window.document.current_tool_id(), window.document.current_mode()) == ("ConvertPage", 2)


def test_the_palette_offers_open_documents_and_recent_files(window, tmp_path):
    path = _pdf(tmp_path / "contrato.pdf")
    window.open_document(path)
    palette = CommandPalette(window.commands(), window, extras=window._palette_extras())
    palette.search.setText("contrato")
    rows = _visible_rows(palette)
    assert rows and {command_group(palette._actions[row]) for row in rows} == {"commands"}

    window.tabs.setCurrentWidget(window.home)
    first = next(row for row in rows if palette._actions[row].objectName().startswith("navigate."))
    palette.list.setCurrentRow(first)
    palette._run()
    palette.chosen.trigger()
    assert window.tabs.currentWidget() is window.document


def test_search_index_entries_cover_every_mode(window):
    entries = search_index.entries()
    modes = sum(len(tool.modes) for tool in TOOLS.values() if len(tool.modes) > 1)
    assert len(entries) == len(TOOLS) + modes


def test_clicking_outside_the_palette_closes_it(window):
    _show(window, 1280, 800)
    palette = CommandPalette(window.commands(), window)
    palette.show()
    QTest.qWait(250)  # a entrada animada (y de 68 a 72) termina
    assert palette.frame.geometry().top() == 72 and palette.frame.width() == 620
    QTest.mouseClick(palette, Qt.MouseButton.LeftButton, pos=QPoint(10, palette.height() - 10))
    assert not palette.isVisible()
