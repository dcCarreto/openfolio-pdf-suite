"""Testes da lista de comentários existentes da aba Anotações (A11)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from reportlab.pdfgen import canvas as rl_canvas

from core.annotations import AddAnnotations, AnnotationSpec, ListAnnotations
from core.redaction import RedactionRect
from core.xfdf import ExportAnnotationsXFDF
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.pages.annotations_page import AnnotationsPage, format_pdf_date
from ui.tasks import wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_pdf(path) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 400))
    canvas.drawString(40, 340, "texto")
    canvas.showPage()
    canvas.save()


def _page_with_comments(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    plain, annotated = tmp_path / "doc.pdf", tmp_path / "anotado.pdf"
    _make_pdf(plain)
    specs = [
        AnnotationSpec(page_index=0, kind="note", position=(300, 300), text="Primeira"),
        AnnotationSpec(page_index=0, kind="highlight", quads=[(40, 335, 90, 352)]),
        AnnotationSpec(page_index=0, kind="stamp", position=(100, 100), text="APROVADO"),
    ]
    AddAnnotations().run(str(plain), str(annotated), specs, author="Ana")
    session = DocumentSession()
    session.open(str(annotated))
    state = AnnotationState()
    return AnnotationsPage(session, state), session, state


def _select(page, *rows):
    page.comments_list.clearSelection()
    for row in rows:
        page.comments_list.item(row).setSelected(True)


def test_comments_are_listed_and_selecting_one_shows_it(tmp_path, monkeypatch):
    page, _session, state = _page_with_comments(tmp_path, monkeypatch)

    assert page.comments_list.count() == 3
    assert page.comments_list.item(0).text().startswith("Página 1 · Nota · Ana")
    _select(page, 0)
    assert page.comment_text_edit.toPlainText() == "Primeira"
    assert state.selected_comment()[0] == 0
    # O texto do carimbo é desenho: não dá para editar pela lista.
    _select(page, 2)
    assert page.comment_text_edit.isReadOnly()
    _select(page, 0, 1)  # dois: as ações vão para a barra acima da lista, e nenhum se abre
    assert page.editor is None and page.comment_text_edit is None
    assert not page.bulk_bar.isHidden() and page.bulk_delete_button.text() == "Excluir 2"
    assert page.bulk_label.text() == "2 selecionados"
    assert state.selected_comment() is None


def test_the_actions_of_a_comment_exist_only_in_it(tmp_path, monkeypatch):
    page, _session, _state = _page_with_comments(tmp_path, monkeypatch)
    assert page.editor is None and page.bulk_bar.isHidden()
    _select(page, 0)
    editor = page.editor
    assert page.comments_list.itemWidget(page.comments_list.item(0)) is editor
    assert "Ana" in editor.title.text() and "pág. 1" in editor.title.text()  # o autor no cabeçalho
    assert [editor.color_button.text(), editor.delete_button.text(), editor.save_button.text()] == [
        "Cor", "Excluir", "Salvar texto",
    ]  # fmt: skip
    assert not editor.save_button.isEnabled()  # nada mudou ainda
    editor.text_edit.setPlainText("Outra")
    assert editor.save_button.isEnabled()
    _select(page, 1)
    assert page.comments_list.itemWidget(page.comments_list.item(0)) is None  # o outro se fecha


def test_the_filter_pills_count_and_filter(tmp_path, monkeypatch):
    page, _session, state = _page_with_comments(tmp_path, monkeypatch)
    state.add_pending(AnnotationSpec(page_index=0, kind="note", position=(9, 9), text="nova"))
    pills = page.filter_buttons
    assert [pills[k].text() for k in ("all", "pending", "saved")] == ["Todos", "Pendentes 1", "Gravados 3"]
    pills["pending"].click()
    shown = [row for row in range(page.comments_list.count()) if not page.comments_list.isRowHidden(row)]
    assert shown == [0]
    pills["saved"].click()
    shown = [row for row in range(page.comments_list.count()) if not page.comments_list.isRowHidden(row)]
    assert shown == [1, 2, 3]


def test_editing_and_removing_create_versions_that_undo_reverts(tmp_path, monkeypatch):
    page, session, _state = _page_with_comments(tmp_path, monkeypatch)

    _select(page, 0)
    page.comment_text_edit.setPlainText("Corrigida")
    page.editor.save_button.click()  # "Salvar texto"
    wait_for_tasks()
    first = ListAnnotations().run(session.path())[0]
    assert (first.content, first.author) == ("Corrigida", "Ana")
    assert page.comment_text_edit.toPlainText() == "Corrigida"  # a seleção volta depois de recarregar

    page._update_comment(author="Bia")  # "Mudar o autor..." do menu do item
    wait_for_tasks()
    assert ListAnnotations().run(session.path())[0].author == "Bia"

    _select(page, 0, 1)
    page._remove_comments()
    wait_for_tasks()
    assert [c.kind for c in ListAnnotations().run(session.path())] == ["FreeText"]
    assert page.comments_list.count() == 1

    session.undo()
    assert page.comments_list.count() == 3


def test_importing_xfdf_adds_the_comments_to_the_open_document(tmp_path, monkeypatch):
    page, session, _state = _page_with_comments(tmp_path, monkeypatch)
    xfdf = tmp_path / "revisao.xfdf"
    ExportAnnotationsXFDF().run(session.path(), str(xfdf))
    blank = tmp_path / "branco.pdf"
    _make_pdf(blank)
    session.open(str(blank))
    assert page.comments_list.count() == 1  # o estado vazio
    assert not page.comments_list.item(0).isSelected()

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(xfdf), ""))
    page._import_xfdf()
    wait_for_tasks()

    assert [c.kind for c in ListAnnotations().run(session.path())] == ["Text", "Highlight", "FreeText"]
    assert page.comments_list.count() == 3
    assert session.can_undo()


def test_format_pdf_date():
    assert format_pdf_date("D:20261019143005-03'00'") == "19/10/2026 14:30"
    assert format_pdf_date("D:20261019") == "19/10/2026"
    assert format_pdf_date("ontem") == ""


def _viewer_with(tmp_path, monkeypatch):
    from ui.redaction_state import RedactionState
    from ui.viewer.pdf_viewer import PdfViewer

    page, session, state = _page_with_comments(tmp_path, monkeypatch)
    viewer = PdfViewer(session, state, RedactionState())
    viewer._show_single_page(0)
    state.set_page_active(True)
    return viewer, page, session, state


def test_dragging_draws_a_shape_with_the_chosen_width(tmp_path, monkeypatch):
    viewer, page, _session, state = _viewer_with(tmp_path, monkeypatch)
    state.set_tool("arrow")  # pela barra de marcação (tests/test_markup_bar.py)
    state.set_width(5)

    viewer._on_canvas_pressed(20, 20)
    viewer._on_canvas_moved(80, 60)
    viewer._on_canvas_released(140, 80)
    viewer._on_canvas_pressed(50, 50)
    viewer._on_canvas_released(51, 50)  # clique sem arrastar: nada

    (spec,) = state.pending()
    assert (spec.kind, spec.width) == ("arrow", 5)
    assert spec.points == [viewer._widget_point_to_pdf(0, 20, 20), viewer._widget_point_to_pdf(0, 140, 80)]


def test_dragging_the_selected_comment_moves_and_resizes_it(tmp_path, monkeypatch):
    viewer, page, session, state = _viewer_with(tmp_path, monkeypatch)
    state.set_tool("select")
    _select(page, 1)  # o realce
    before = ListAnnotations().run(session.path())[1].rect
    screen = viewer._user_rect_to_screen(0, before)

    viewer._on_canvas_pressed(screen.center().x(), screen.center().y())
    viewer._on_canvas_moved(screen.center().x() + 30, screen.center().y() + 60)
    viewer._on_canvas_released(screen.center().x() + 30, screen.center().y() + 60)
    wait_for_tasks()

    moved = ListAnnotations().run(session.path())[1]
    scale = viewer._scale
    assert moved.kind == "Highlight"
    assert moved.rect[0] - before[0] == pytest.approx(30 / scale, abs=0.5)
    assert moved.rect[1] - before[1] == pytest.approx(-60 / scale, abs=0.5)  # para baixo na tela
    assert moved.rect[2] - moved.rect[0] == pytest.approx(before[2] - before[0], abs=0.5)

    _select(page, 1)
    screen = viewer._user_rect_to_screen(0, moved.rect)
    corner = screen.bottomRight()
    viewer._on_canvas_pressed(corner.x() - 2, corner.y() - 2)
    viewer._on_canvas_moved(corner.x() + 40, corner.y() - 2)
    viewer._on_canvas_released(corner.x() + 40, corner.y() - 2)
    wait_for_tasks()

    resized = ListAnnotations().run(session.path())[1]
    assert resized.rect[2] - resized.rect[0] == pytest.approx(moved.rect[2] - moved.rect[0] + 42 / scale, abs=0.5)
    session.undo()
    session.undo()
    assert ListAnnotations().run(session.path())[1].rect == before


def test_recolor_and_author_of_new_annotations(tmp_path, monkeypatch):
    from ui.preferences import Preferences

    monkeypatch.setattr("ui.preferences._current", Preferences())  # em memória, só neste teste
    shown = []
    page, session, state = _page_with_comments(tmp_path, monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text, *a: shown.append(text))
    stamp_color = ListAnnotations().run(session.path())[2].color
    state.set_color("2196f3")
    _select(page, 0, 1, 2)
    page._recolor_comments()
    wait_for_tasks()

    assert [c.color for c in ListAnnotations().run(session.path())] == ["2196f3", "2196f3", stamp_color]
    assert "Cor trocada em 2 comentários." in shown[-1] and "1 ficou como estava" in shown[-1]

    page.author_edit.setText("Revisora")
    page.author_edit.editingFinished.emit()
    assert AnnotationsPage(session, state).author_edit.text() == "Revisora"  # fica guardado


def test_window_ctrl_z_undoes_and_redoes_pending_marks(tmp_path):
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    _app()
    _make_pdf(tmp_path / "doc.pdf")
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    try:
        window.open_document(str(tmp_path / "doc.pdf"))
        window.open_tool(window._row_of["AnnotationsPage"])
        state = window.annotation_state
        first = AnnotationSpec(page_index=0, kind="note", position=(10, 10), text="a")
        second = AnnotationSpec(page_index=0, kind="ink", points=[(10, 10), (50, 50)])
        state.add_pending(first)
        state.add_pending(second)
        assert window._undo_action.isEnabled() and window._undo_action.text() == "Desfazer anotação"

        window.show()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window)  # o atalho só chega à janela ativa
        window.viewer.setFocus()
        QTest.keyClick(window.viewer, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert state.pending() == [first]  # pelo atalho, a última some primeiro
        window.undo()
        assert state.pending() == [] and window._redo_action.isEnabled()
        window.redo()
        assert state.pending() == [first]

        state.add_pending(second)  # anotação nova apaga o "refazer"
        assert not window._redo_action.isEnabled()
        state.clear_pending()  # "Descartar" também se desfaz
        window.undo()
        assert state.pending() == [first, second]

        window.session.open(str(tmp_path / "doc.pdf"))  # outro arquivo: nada a desfazer dele
        assert state.pending() == [] and not window._undo_action.isEnabled()

        window.open_tool(window._row_of["RedactionPage"])
        area = RedactionRect(page_index=0, left=10, bottom=10, right=50, top=50)
        window.redaction_state.add_pending(area)
        assert window._undo_action.text() == "Desfazer área de redação"
        window.undo()
        assert window.redaction_state.pending() == []
        window.redo()
        assert window.redaction_state.pending() == [area]
    finally:
        window.close()
