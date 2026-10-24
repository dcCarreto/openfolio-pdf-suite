"""A estrutura da janela: barra superior, abas, aba de documento e o que muda com a largura."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QTabBar, QWidget

from ui import i18n, theme
from ui.main_window import MainWindow

# As ações da janela e os atalhos de fábrica antes da barra superior nova: nada pode sumir.
_COMMANDS_BEFORE = [
    ("file.open", ["Ctrl+O"]),
    ("file.save", ["Ctrl+S"]),
    ("file.save_as", ["Ctrl+Shift+S"]),
    ("file.print", ["Ctrl+P"]),
    ("file.properties", ["Ctrl+D"]),
    ("file.close_tab", ["Ctrl+W"]),
    ("file.quit", ["Ctrl+Q"]),
    ("edit.undo", ["Ctrl+Z"]),
    ("edit.redo", ["Ctrl+Y", "Ctrl+Shift+Z"]),
    ("edit.shortcuts", []),
    ("view.home", []),
    ("view.tools", ["Shift+F4"]),
    ("view.palette", ["Ctrl+K"]),
    ("view.presentation", ["F5", "Ctrl+L"]),
    ("view.layout.single", []),
    ("view.layout.continuous", []),
    ("view.layout.double", []),
    ("view.layout.book", []),
    ("view.theme.dark", []),
    ("view.theme.light", []),
    ("view.theme.system", []),
    ("view.animations", []),
    ("help.check_updates", []),
    ("help.check_updates_on_start", []),
    ("help.about", []),
] + [
    (f"tool.{name}", [])
    for name in (
        "CreatePage MergePage SplitPage PagesPage OrganizePage CompressPage ConvertPage WatermarkPage ProtectPage "
        "MetadataPage PageNumbersPage PDFAPage ExtractTextPage ExtractImagesPage CropPage EditPage BookmarksPage "
        "LayersPage AttachmentsPage FormFieldsPage AnnotationsPage MeasurePage OCRPage ScanCleanupPage RedactionPage "
        "FillSignPage SignaturePage AccessibilityPage ComparePage BatchPage"
    ).split()
]


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, theme.DARK)
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield window
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.close()
    i18n.set_language(i18n.PT_BR)
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())


def _pdf(path, pages=3):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    writer.write(str(path))
    return str(path)


def _show(window, width, height):
    window.resize(width, height)
    window.show()
    QApplication.processEvents()


def test_every_menu_action_and_shortcut_is_still_there(window):
    found = [(action.objectName(), [key.toString() for key in action.shortcuts()]) for _label, action in window.commands()]
    assert found == _COMMANDS_BEFORE


def test_one_top_bar_holds_logo_menus_tabs_launcher_and_language(window):
    top_bar = window.menuWidget()
    assert top_bar.objectName() == "TopBar" and top_bar.height() == 44
    assert window.menuBar().objectName() == "MainMenu" and window.menuBar().parent() is top_bar
    assert [action.text() for action in window.menuBar().actions()] == ["Arquivo", "Editar", "Exibir", "Ajuda"]
    assert window.tabs.tabBar().parent() is top_bar
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Início", "Ferramentas"]
    window.tabs.setCurrentWidget(window.tools_center)
    window._logo_button.click()
    assert window.tabs.currentWidget() is window.home


def test_the_launcher_opens_the_command_palette(window, monkeypatch):
    from ui import main_window

    opened = []
    monkeypatch.setattr(main_window.CommandPalette, "exec", lambda palette: opened.append(palette) or 0)
    window._command_launcher.click()
    assert opened


def test_language_switch_translates_the_new_bar_live(window):
    switch = window._language_switcher
    assert switch.buttons[i18n.PT_BR].isChecked()

    switch.buttons[i18n.EN_US].click()

    assert switch.buttons[i18n.EN_US].isChecked()
    assert [window.tabs.tabText(i) for i in range(2)] == ["Home", "Tools"]
    assert window._command_launcher.text() == "Search tools and commands"
    assert [action.text() for action in window.menuBar().actions()] == ["File", "Edit", "View", "Help"]


def test_document_tabs_reorder_but_home_and_tools_stay_first(window, tmp_path):
    first = window.open_document(_pdf(tmp_path / "um.pdf"))
    second = window.open_document(_pdf(tmp_path / "dois.pdf"))
    bar = window.tabs.tabBar()

    bar.moveTab(3, 2)  # arrastar "dois" para antes de "um"
    assert [window.tabs.widget(i) for i in range(4)] == [window.home, window.tools_center, second, first]
    assert window.tabs.currentWidget() is second and window.document is second

    bar.moveTab(2, 0)  # soltar antes do Início: ao soltar, as fixas voltam para a frente
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(0).center())
    assert [window.tabs.tabText(i) for i in range(4)] == ["Início", "Ferramentas", "dois.pdf", "um.pdf"]
    assert [window.tabs.widget(i) for i in range(4)] == [window.home, window.tools_center, second, first]

    assert window.close_document(first)
    assert [window.tabs.widget(i) for i in range(3)] == [window.home, window.tools_center, second]


def test_a_running_operation_spins_in_the_tab(window, tmp_path, monkeypatch):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    bar = window.tabs.tabBar()
    index = window.tabs.indexOf(doc)

    monkeypatch.setattr(doc.tasks, "is_busy", lambda: True)
    window._update_tab(doc)
    assert bar.tabButton(index, QTabBar.ButtonPosition.LeftSide) is doc.busy_spinner
    assert bar.tabIcon(index).isNull()

    monkeypatch.setattr(doc.tasks, "is_busy", lambda: False)
    window._update_tab(doc)
    assert bar.tabButton(index, QTabBar.ButtonPosition.LeftSide) is None and not bar.tabIcon(index).isNull()


def test_the_document_tab_layout(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1600, 900)

    assert doc.left_rail.width() == 48 and doc.right_rail.width() == 52
    assert doc.viewer.toolbar.parent() is doc.center and doc.viewer.toolbar.height() == 44
    assert window.statusBar().objectName() == "StatusBar" and window.statusBar().height() == 28
    assert doc.splitter.widget(2) is doc.tool_panel and doc.tool_header.parent() is doc.tool_panel


def test_a_tool_in_a_1280_window_folds_the_thumbnails_and_gives_them_back(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1280, 800)
    side_panel = doc.viewer.side_panel
    assert side_panel.isVisible() and doc._left_buttons[0].isChecked()

    doc.open_tool(window._row_of["CompressPage"])
    QApplication.processEvents()
    assert not side_panel.isVisible() and not doc._left_buttons[0].isChecked()

    doc.close_tool()
    QApplication.processEvents()
    assert side_panel.isVisible() and doc._left_buttons[0].isChecked()


def test_a_wide_window_keeps_the_thumbnails_with_a_tool_open(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1600, 900)

    doc.open_tool(window._row_of["CompressPage"])
    QApplication.processEvents()
    assert doc.viewer.side_panel.isVisible()


def test_a_narrow_window_compacts_the_bars(window, tmp_path):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    _show(window, 1024, 720)

    assert doc.viewer.more_button.isVisible() and not doc.viewer.single_page_button.isVisible()
    assert window._command_launcher.text() == "" and window._command_launcher.width() == 32
    assert window.tabs.tabBar().property("compact")

    _show(window, 1440, 900)
    assert not doc.viewer.more_button.isVisible() and doc.viewer.single_page_button.isVisible()
    assert window._command_launcher.text() == "Buscar ferramentas e comandos"


def _visible_children(parent: QWidget) -> list[QWidget]:
    layout = parent.layout()
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    return [w for w in widgets if w is not None and w.isVisible()]


def _assert_side_by_side(parent: QWidget):
    """Cada item visível da barra começa depois do anterior e cabe nela."""
    widgets = sorted(_visible_children(parent), key=lambda w: w.x())
    for before, after in zip(widgets, widgets[1:]):
        assert before.geometry().right() < after.x(), (before, after)
    assert widgets[-1].geometry().right() <= parent.width()


@pytest.mark.parametrize("key", [theme.DARK, theme.LIGHT])
@pytest.mark.parametrize("size", [(1920, 1080), (1440, 900), (1280, 800), (1024, 720)])
def test_nothing_overlaps_from_1920_to_1024(window, tmp_path, key, size):
    theme.apply_theme(QApplication.instance(), key)
    doc = window.open_document(_pdf(tmp_path / "doc.pdf"))
    doc.open_tool(window._row_of["CompressPage"])
    _show(window, *size)

    _assert_side_by_side(window.menuWidget())
    _assert_side_by_side(doc.viewer.toolbar)
    assert doc.center.width() >= 320
    assert doc.tool_panel.geometry().right() < doc.right_rail.mapTo(doc, doc.right_rail.rect().topLeft()).x()
    window.grab().save(str(tmp_path / f"{key}-{size[0]}x{size[1]}.png"))  # para olhar quando falhar
