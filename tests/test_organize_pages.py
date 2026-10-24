"""Editor de páginas (A03): ArrangePages e a aba Organizar páginas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication

from core.pages import ArrangePages
from ui.document_session import DocumentSession
from ui.pages.organize_page import OrganizePage
from ui.tasks import wait_for_tasks


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pages(path) -> list[tuple[int, int, int]]:
    """(largura, altura, giro) de cada página."""
    return [
        (round(float(page.mediabox.width)), round(float(page.mediabox.height)), page.rotation)
        for page in PdfReader(str(path)).pages
    ]


def test_arrange_reorders_duplicates_rotates_removes_and_adds_blanks(make_pdf, tmp_path):
    source = make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 400)])
    output = tmp_path / "saida.pdf"
    ArrangePages().run(str(source), str(output), [(2, 0), (0, 90), (None, 0), (0, 0)])
    # A página 2 saiu; a em branco tem o tamanho da anterior como ela aparece (girada).
    assert _pages(output) == [(300, 400, 0), (100, 300, 90), (300, 100, 0), (100, 300, 0)]


def test_arrange_blank_first_takes_the_size_of_the_next_page(make_pdf, tmp_path):
    source = make_pdf("doc.pdf", [(100, 300)])
    output = tmp_path / "saida.pdf"
    ArrangePages().run(str(source), str(output), [(None, 0), (0, 0)])
    assert _pages(output) == [(100, 300, 0), (100, 300, 0)]


@pytest.mark.parametrize(
    ("layout", "message"),
    [([], "sem nenhuma página"), ([(5, 0)], "5|6"), ([(0, 45)], "múltiplo de 90")],
)
def test_arrange_rejects_invalid_layouts(make_pdf, tmp_path, layout, message):
    source = make_pdf("doc.pdf", [(100, 300)])
    with pytest.raises(ValueError, match=message):
        ArrangePages().run(str(source), str(tmp_path / "x.pdf"), layout)


@pytest.fixture
def organizer(make_pdf):
    _app()
    session = DocumentSession()
    session.open(str(make_pdf("doc.pdf", [(100, 300), (200, 300), (300, 300)])))
    page = OrganizePage(session)
    page.render_all()
    return page


def _select(page, *rows):
    page._select_rows(list(rows))


def test_grid_edits_stay_pending_until_applied(organizer):
    page, session = organizer, organizer.session
    assert page.layout_items() == [(0, 0), (1, 0), (2, 0)]
    assert not page.apply_button.isEnabled()

    _select(page, 0)
    page.rotate_selected(90)
    page.duplicate_selected()  # a cópia herda o giro e fica selecionada
    page.move_selected(1)
    _select(page, 1)
    page.delete_selected()
    page.insert_blank()  # sem seleção: no fim
    assert page.layout_items() == [(0, 90), (0, 90), (2, 0), (None, 0)]
    assert page.apply_button.isEnabled()
    assert _pages(session.path()) == [(100, 300, 0), (200, 300, 0), (300, 300, 0)]

    page.apply_button.click()
    assert wait_for_tasks()
    assert _pages(session.path()) == [(100, 300, 90), (100, 300, 90), (300, 300, 0), (300, 300, 0)]
    # A grade passa a mostrar o documento novo, sem nada pendente; Ctrl+Z volta tudo.
    assert page.layout_items() == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert not page.apply_button.isEnabled()
    session.undo()
    assert page.layout_items() == [(0, 0), (1, 0), (2, 0)]


def test_dragging_a_thumbnail_moves_the_page(organizer):
    page = organizer
    # O que o arrastar faz no modelo da grade (modo lista com InternalMove).
    assert page.grid.model().moveRow(QModelIndex(), 0, QModelIndex(), 3)
    assert page.layout_items() == [(1, 0), (2, 0), (0, 0)]
    assert page.apply_button.isEnabled()


def test_discard_restores_the_document_order(organizer):
    page = organizer
    _select(page, 1)
    page.delete_selected()
    page.discard_button.click()
    assert page.layout_items() == [(0, 0), (1, 0), (2, 0)]
    assert not page.discard_button.isEnabled()


def test_extract_saves_the_selected_pages_with_their_edits(organizer, tmp_path):
    page = organizer
    _select(page, 2)
    page.rotate_selected(270)
    _select(page, 0, 2)
    target = tmp_path / "extraidas.pdf"
    assert page.extract_to(str(target), [tuple(page.grid.item(row).data(0x0100)) for row in (0, 2)])
    assert wait_for_tasks()
    assert _pages(target) == [(100, 300, 0), (300, 300, 270)]
    assert "2" in page.status_label.text()
    assert len(PdfReader(page.session.path()).pages) == 3  # o documento não muda


def test_grid_edits_can_be_undone_and_redone_before_applying(organizer):
    page = organizer
    assert not page.can_undo_edit()
    _select(page, 0)
    page.rotate_selected(90)
    page.grid.model().moveRow(QModelIndex(), 2, QModelIndex(), 0)  # arrastar também conta
    assert page.layout_items() == [(2, 0), (0, 90), (1, 0)]

    page.undo_edit()
    assert page.layout_items() == [(0, 90), (1, 0), (2, 0)]
    page.undo_edit()
    assert page.layout_items() == [(0, 0), (1, 0), (2, 0)]
    assert not page.can_undo_edit() and not page.apply_button.isEnabled()
    page.redo_edit()
    assert page.layout_items() == [(0, 90), (1, 0), (2, 0)]
    _select(page, 1)
    page.delete_selected()  # mudança nova apaga o "refazer"
    assert not page.can_redo_edit()


def test_window_ctrl_z_undoes_grid_edits_first(make_pdf, tmp_path):
    from PySide6.QtCore import QSettings

    from ui.main_window import MainWindow

    _app()
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    try:
        window.session.open(str(make_pdf("doc.pdf", [(100, 300), (200, 300)])))
        row = window._row_of["OrganizePage"]
        page = window.open_tool(row)
        assert not window._undo_action.isEnabled()

        _select(page, 1)
        page.delete_selected()
        page.apply_button.click()
        assert wait_for_tasks()
        _select(page, 0)
        page.rotate_selected(90)
        assert window._undo_action.isEnabled()
        assert window._undo_action.text() == "Desfazer edição na grade"

        window.undo()  # a grade primeiro
        assert page.layout_items() == [(0, 0)]
        assert window.session.can_undo()
        window.undo()  # depois o documento
        assert page.layout_items() == [(0, 0), (1, 0)]
        assert not window._undo_action.isEnabled()
    finally:
        window.close()
