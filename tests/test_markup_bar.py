"""A barra de marcação sobre o visualizador e o painel de Anotações (comentários e rodapé)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfWriter
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLineEdit,
    QMessageBox,
)

from core.annotations import AddAnnotations, AnnotationSpec, ListAnnotations
from ui import i18n, motion, theme
from ui.annotation_state import TOOLS
from ui.document_tab import DRAWER_WIDTH
from ui.main_window import MainWindow
from ui.tasks import wait_for_tasks
from ui.viewer.markup_bar import DEFAULT_KEYS, GROUPS, TOP_INSET


@pytest.fixture
def window(tmp_path, monkeypatch):
    theme.apply_theme(QApplication.instance() or QApplication([]), theme.DARK)  # medidas do app de verdade
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


def _annotations(window, tmp_path, pages=2):
    doc = window.open_document(_pdf(tmp_path / "doc.pdf", pages))
    window.open_tool(window._row_of["AnnotationsPage"])
    return doc, doc.markup_bar, doc.annotation_state


def _show(window, width, height):
    window.resize(width, height)
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    QTest.qWait(250)  # as animações (120-160 ms) terminam


def test_the_bar_shows_only_with_annotations_open_on_a_document(window, tmp_path):
    window.open_tool(window._row_of["AnnotationsPage"])
    doc = window.document
    assert not doc.markup_bar.isVisibleTo(doc)  # sem documento, nada a marcar

    window.open_document(_pdf(tmp_path / "doc.pdf"))
    assert doc.markup_bar.isVisibleTo(doc) and doc.viewer._top_inset == TOP_INSET

    doc.close_tool()
    assert not doc.markup_bar.isVisibleTo(doc) and doc.viewer._top_inset == 0


def test_the_bar_is_grouped_on_one_line(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    _show(window, 1440, 900)
    room = doc.viewer.scroll_area.viewport().width()
    assert not bar.is_compact(), f"barra {bar.full_width()} px, centro {room} px"
    assert [group.tools for group in bar.groups] == list(GROUPS)
    assert bar.height() == 42  # uma linha só: botões de 32, 4 de folga e a borda
    tops = {group.mapTo(bar, QPoint(0, 0)).y() for group in bar.groups}
    assert len(tops) == 1 and bar.style_button.mapTo(bar, QPoint(0, 0)).y() in tops


def test_every_markup_tool_is_chosen_from_the_bar(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    for tool in TOOLS:
        group = bar.group_of[tool]
        if tool == group.tools[0]:
            group.button.click()
        else:
            group.tool_actions[tool].trigger()  # no ▾ do grupo
        assert state.active_tool() == tool
        assert [g.tools for g in bar.groups if g.button.isChecked()] == [group.tools]
        assert group.current == tool and not group.button.text()  # só ícone
        assert f"({DEFAULT_KEYS[tool]})" in group.button.toolTip()

    bar.group_of["highlight"].tool_actions["underline"].trigger()
    state.set_tool("ink")
    bar.button_for("highlight").click()  # o botão do Realce lembra a última escolhida do grupo
    assert state.active_tool() == "underline"
    bar.button_for("underline").click()  # clicar na ativa não a desmarca
    assert bar.button_for("underline").isChecked()


def test_the_group_menus_show_the_keys(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    actions = bar.group_of["highlight"].tool_actions
    assert actions["underline"].text() == "Sublinhado\tU" and actions["strikeout"].text() == "Riscado\tS"
    state.set_tool("circle")
    assert not actions["highlight"].isChecked() and bar.group_of["circle"].tool_actions["circle"].isChecked()


def test_color_and_thickness_from_the_bar(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    i18n.set_language(i18n.PT_BR)

    bar.color_buttons["2196f3"].click()
    assert state.active_color() == "2196f3"
    bar.width_up.click()
    assert state.width() == 3.0 and bar.width_label.text() == "3 pt"
    bar.width_down.click()
    bar.width_down.click()
    assert bar.width_label.text() == "2 pt"
    state.set_width(2.5)
    assert bar.width_label.text() == "2,5 pt"

    state.set_tool("highlight")  # segue a linha do texto: sem espessura
    assert not bar.width_control.isEnabled() and bar.width_control.toolTip()
    state.set_tool("ink")
    assert bar.width_control.isEnabled()

    state.set_color("123456")  # um carimbo salvo com cor própria
    assert bar.custom_color_button.isChecked() and bar.custom_color_button.color == "123456"
    assert bar.style_group.parentWidget() is bar.style_popover  # cor e espessura no popover do Estilo
    bar.style_button.click()
    assert bar.style_popover.isVisible()
    bar.style_popover.hide()


def test_the_pending_counter_follows_undo_and_redo(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    _show(window, 1440, 900)
    assert not bar.pending_label.isVisibleTo(bar) and not bar.save_button.isEnabled()

    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(50, 50), text="a"))
    state.add_pending(AnnotationSpec(page_index=0, kind="ink", points=[(10, 10), (60, 60)]))
    assert bar.pending_label.isVisibleTo(bar) and bar.pending_label.text() == "2 pendentes"
    assert bar.save_button.isEnabled()

    window.undo()
    assert bar.pending_label.text() == "1 pendente"
    window.redo()
    assert bar.pending_label.text() == "2 pendentes"
    state.clear_pending()
    assert not bar.pending_label.isVisibleTo(bar) and not bar.save_button.isEnabled()


def test_save_on_the_bar_makes_a_version_that_undo_names(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(50, 50), text="ver"))

    bar.save_button.click()
    assert wait_for_tasks()

    assert state.pending() == []
    assert window._undo_action.text() == "Desfazer Gravar marcações"
    assert [c.kind for c in ListAnnotations().run(doc.session.path())] == ["Text"]


def test_single_keys_choose_tools_only_from_the_viewer(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    _show(window, 1440, 900)
    canvas = doc.viewer.scroll_area

    canvas.setFocus()
    QTest.keyClick(canvas, Qt.Key.Key_H)
    assert state.active_tool() == "highlight"
    QTest.keyClick(canvas, Qt.Key.Key_K)
    assert state.active_tool() == "stamp"

    editor = QLineEdit(canvas.viewport())  # um campo de texto sobre a página (formulário)
    editor.show()
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_S)
    assert editor.text() == "s" and state.active_tool() == "stamp"  # o campo fica com a tecla

    doc.close_tool()
    canvas.setFocus()
    QTest.keyClick(canvas, Qt.Key.Key_U)
    assert state.active_tool() == "stamp"  # sem Anotações aberta, a tecla não faz nada


def test_the_keys_are_configurable_and_the_bar_shows_them(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    commands = {action.objectName(): action for _label, action in window.commands()}
    assert commands["markup.highlight"].shortcut().toString() == "H"

    window._preferences.set_shortcut("markup.highlight", "G")
    window._apply_shortcuts()
    state.set_tool("highlight")

    assert "(G)" in bar.button_for("highlight").toolTip()
    assert bar.group_of["highlight"].tool_actions["highlight"].text() == "Realce\tG"


@pytest.mark.parametrize("tool", ["ink", "select"])  # página única (desenho) e rolagem contínua
def test_the_bar_does_not_cover_the_page(window, tmp_path, tool):
    doc, bar, state = _annotations(window, tmp_path)
    state.set_tool(tool)
    _show(window, 1440, 900)
    viewport = doc.viewer.scroll_area.viewport()
    doc.viewer.scroll_area.verticalScrollBar().setValue(0)

    label = doc.viewer._page_labels[0]
    offset = label.pixmap_offset().y() if hasattr(label, "pixmap_offset") else 0
    page_top = label.mapTo(viewport, QPoint(0, int(offset))).y()
    assert page_top >= bar.geometry().bottom()


def test_wide_window_full_bar_narrow_window_compact(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(50, 50), text="a"))
    _show(window, 1440, 900)
    assert not bar.is_compact() and not doc.viewer.side_panel.isVisible()  # as miniaturas cedem antes
    wide = bar.style_button.width()

    _show(window, 1000, 640)
    assert doc.is_drawer_open()  # centralizada na parte visível, à esquerda da gaveta
    assert bar.geometry().right() <= doc.viewer.scroll_area.viewport().width() - DRAWER_WIDTH
    assert bar.geometry().left() >= 0 and bar.full_width() <= bar.parentWidget().width() - DRAWER_WIDTH

    bar.set_compact(True)  # sem espaço: o Estilo sem a espessura escrita e o contador só com o número
    assert bar.style_button.width() < wide and bar.pending_label.text() == "1"
    assert bar.full_width() > bar.sizeHint().width()  # a inteira continua medida para voltar

    _show(window, 1440, 900)
    assert not bar.is_compact() and bar.pending_label.text() == "1 pendente"


def test_the_bar_fades_while_reading_and_comes_back(window, tmp_path, monkeypatch):
    monkeypatch.setattr(motion, "enabled", lambda: True)
    doc, bar, state = _annotations(window, tmp_path)
    _show(window, 1440, 900)
    state.set_tool("select")

    bar.note_scroll()
    assert bar._fade_timer.isActive()
    bar._fade_out()  # passou 1,5 s sem mexer na barra
    QTest.qWait(250)
    assert isinstance(bar.graphicsEffect(), QGraphicsOpacityEffect) and bar.graphicsEffect().opacity() < 1

    state.set_tool("ink")  # trocar de ferramenta traz a barra de volta
    QTest.qWait(250)
    assert isinstance(bar.graphicsEffect(), QGraphicsDropShadowEffect)

    monkeypatch.setattr(motion, "enabled", lambda: False)  # animações desligadas: fica sempre inteira
    state.set_tool("select")
    bar.note_scroll()
    assert not bar._fade_timer.isActive()


def test_the_comments_list_marks_pending_and_saved(window, tmp_path):
    plain = _pdf(tmp_path / "plain.pdf")
    annotated = str(tmp_path / "anotado.pdf")
    AddAnnotations().run(plain, annotated, [AnnotationSpec(page_index=1, kind="note", position=(9, 9), text="Gravada")])
    doc = window.open_document(annotated)
    page = window.open_tool(window._row_of["AnnotationsPage"])
    state = doc.annotation_state
    state.add_pending(AnnotationSpec(page_index=0, kind="highlight", quads=[(10, 10, 90, 30)], color="ffeb3b"))

    rows = [page.comments_list.item(row) for row in range(page.comments_list.count())]
    assert page.comments_title.text() == "Comentários · 2"
    assert [row.data(Qt.ItemDataRole.UserRole + 1)[4] for row in rows] == [True, False]  # pendente, gravado
    assert "Pendente" in rows[0].text() and "Gravada" not in rows[0].text()

    spy = QSignalSpy(state.page_requested)
    rows[0].setSelected(True)
    assert spy.count() == 1  # clicar numa pendente mostra a página dela

    doc.session.set_current_page(1)
    page.page_filter.setCurrentIndex(1)  # "Página atual"
    assert page.comments_list.isRowHidden(0) and not page.comments_list.isRowHidden(1)


def test_the_panel_footer_discards_and_counts_the_markups(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    panel = doc.current_panel()
    page = doc.page(window._row_of["AnnotationsPage"])
    assert panel.isAncestorOf(page.discard_button) and panel.footer.isAncestorOf(page.discard_button)
    assert not panel.primary_button.isEnabled()

    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(50, 50), text="a"))
    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(80, 80), text="b"))
    assert panel.primary_button.text() == "Gravar 2 marcações" and panel.primary_button.isEnabled()

    page.discard_button.click()
    assert state.pending() == []
    window.undo()  # descartar também se desfaz
    assert len(state.pending()) == 2


def test_switching_language_translates_the_bar(window, tmp_path):
    doc, bar, state = _annotations(window, tmp_path)
    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(50, 50), text="a"))
    _show(window, 1440, 900)
    try:
        i18n.set_language(i18n.EN_US)
        assert bar.save_button.text() == "Save" and bar.pending_label.text() == "1 pending"
        assert bar.button_for("ink").accessibleName() == "Pen"
    finally:
        i18n.set_language(i18n.PT_BR)
    assert bar.save_button.text() == "Gravar"


def test_comment_rows_fit_the_list_width(window, tmp_path):
    plain = _pdf(tmp_path / "plain.pdf")
    annotated = str(tmp_path / "anotado.pdf")
    long_text = "Um comentário bem comprido que passaria da largura do painel " * 3
    AddAnnotations().run(plain, annotated, [AnnotationSpec(page_index=0, kind="note", position=(9, 9), text=long_text)],
                         author="Revisora com um nome longo")
    window.open_document(annotated)
    page = window.open_tool(window._row_of["AnnotationsPage"])
    _show(window, 1440, 900)
    rows = page.comments_list
    rect = rows.visualRect(rows.model().index(0, 0))
    assert rect.right() <= rows.viewport().width() and rows.horizontalScrollBar().maximum() == 0
