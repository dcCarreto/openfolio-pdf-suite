import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.bookmarks import AddBookmarks


def test_add_bookmarks(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200), (200, 200)])
    output_path = tmp_path / "bookmarked.pdf"

    AddBookmarks().run(
        str(pdf_path),
        str(output_path),
        bookmarks=[("Capítulo 1", 0), ("Capítulo 2", 2)],
    )

    reader = PdfReader(str(output_path))
    outline = reader.outline
    assert len(outline) == 2
    assert outline[0].title == "Capítulo 1"
    assert outline[1].title == "Capítulo 2"


def test_add_bookmarks_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddBookmarks().run(str(encrypted_path), str(tmp_path / "out.pdf"), bookmarks=[("Cap", 0)])


def _outline(path):
    from core.bookmarks import ListOutline

    return [(item.level, item.title, item.page_index) for item in ListOutline().run(str(path))]


def test_set_outline_writes_the_tree_and_drops_the_old_one(make_pdf, tmp_path):
    from core.bookmarks import OutlineItem, SetOutline

    pdf_path = make_pdf("doc.pdf", [(200, 200)] * 4)
    old = tmp_path / "antigo.pdf"
    AddBookmarks().run(str(pdf_path), str(old), bookmarks=[("Demissao de Fulano", 1)])
    output_path = tmp_path / "novo.pdf"

    SetOutline().run(
        str(old),
        str(output_path),
        [
            OutlineItem(0, "Parte 1", 0),
            OutlineItem(1, "Capítulo 1", 1),
            OutlineItem(2, "Seção 1.1", 2),
            OutlineItem(1, "Capítulo 2", 3),
            OutlineItem(0, "Sem página", None),
        ],
    )

    assert _outline(output_path) == [
        (0, "Parte 1", 0), (1, "Capítulo 1", 1), (2, "Seção 1.1", 2), (1, "Capítulo 2", 3), (0, "Sem página", None),
    ]  # fmt: skip
    assert b"Demissao de Fulano" not in output_path.read_bytes()  # o título apagado não fica nos bytes


def test_set_outline_rejects_a_level_that_skips_a_parent(make_pdf, tmp_path):
    from core.bookmarks import OutlineItem, SetOutline

    with pytest.raises(ValueError):
        SetOutline().run(str(make_pdf("doc.pdf", [(200, 200)])), str(tmp_path / "o.pdf"), [OutlineItem(1, "Órfão", 0)])


def test_an_empty_outline_removes_every_bookmark(make_pdf, tmp_path):
    from core.bookmarks import SetOutline

    marked = tmp_path / "marcado.pdf"
    AddBookmarks().run(str(make_pdf("doc.pdf", [(200, 200)])), str(marked), bookmarks=[("Cap", 0)])

    SetOutline().run(str(marked), str(tmp_path / "o.pdf"), [])

    assert _outline(tmp_path / "o.pdf") == []


def test_headings_are_detected_by_font_size(tmp_path):
    from reportlab.pdfgen import canvas as rl_canvas

    from core.bookmarks import DetectHeadings

    path = tmp_path / "relatorio.pdf"
    canvas = rl_canvas.Canvas(str(path), pagesize=(595, 842))
    body = "Texto do corpo do relatório, comprido o bastante para ser a fonte mais usada."

    def write(size, text, y):
        canvas.setFont("Helvetica", size)
        canvas.drawString(50, y, text)

    write(14, "Introdução ao relatório", 780)  # subtítulo antes de qualquer título: fica no topo
    for y in range(740, 400, -20):
        write(10, body, y)
    canvas.showPage()
    write(24, "1 Resultados", 780)
    write(14, "1.1 Vendas do ano", 740)
    write(10, body, 700)
    write(10, "42", 680)
    write(24, "123", 640)  # número grande sozinho (um valor em destaque) não é título
    canvas.showPage()
    canvas.save()

    items = DetectHeadings().run(str(path))

    assert [(i.level, i.title, i.page_index) for i in items] == [
        (0, "Introdução ao relatório", 0), (0, "1 Resultados", 1), (1, "1.1 Vendas do ano", 1),
    ]  # fmt: skip


def test_bookmarks_tab_loads_edits_nests_and_saves(make_pdf, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.bookmarks import OutlineItem, SetOutline
    from ui.document_session import DocumentSession
    from ui.pages.bookmarks_page import BookmarksPage
    from ui.tasks import wait_for_tasks
    from ui.widget_state import capture_state, restore_state

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    source = tmp_path / "marcado.pdf"
    SetOutline().run(
        str(make_pdf("doc.pdf", [(200, 200)] * 4)),
        str(source),
        [OutlineItem(0, "A", 0), OutlineItem(0, "B", 1), OutlineItem(1, "B1", 2)],
    )
    session = DocumentSession()
    session.open(str(source))
    page = BookmarksPage(session)
    assert page.items() == [(0, "A", "1"), (0, "B", "2"), (1, "B1", "3")]  # o que o documento já tem

    page.tree.setCurrentItem(page.tree.topLevelItem(1))
    page._indent()  # B (com B1) entra em A
    page.tree.setCurrentItem(page.tree.topLevelItem(0).child(0).child(0))
    page._outdent()  # B1 sai de B, fica depois dele dentro de A
    page._move(-1)  # e sobe para antes de B
    page.tree.topLevelItem(0).child(0).setText(0, "B1 renomeado")
    page.title_edit.setText("Fim")
    page.page_spin.setValue(4)
    page._add_bookmark()
    assert page.items() == [(0, "A", "1"), (1, "B1 renomeado", "3"), (1, "B", "2"), (0, "Fim", "4")]

    rebuilt = BookmarksPage(session)  # a troca de idioma reconstrói a aba
    restore_state(rebuilt, capture_state(page))
    assert rebuilt.items() == page.items()

    output = tmp_path / "saida.pdf"
    monkeypatch.setattr(rebuilt.output_picker, "path", lambda: str(output))
    rebuilt._save()
    assert wait_for_tasks()
    assert _outline(output) == [(0, "A", 0), (1, "B1 renomeado", 2), (1, "B", 1), (0, "Fim", 3)]


def test_bookmarks_tab_refuses_a_page_that_does_not_exist(make_pdf, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.document_session import DocumentSession
    from ui.pages.bookmarks_page import BookmarksPage
    from ui.tasks import wait_for_tasks

    QApplication.instance() or QApplication([])
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, _t, text, *a: errors.append(text))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a: errors.append(text))
    session = DocumentSession()
    session.open(str(make_pdf("doc.pdf", [(200, 200)] * 2)))
    page = BookmarksPage(session)
    page.title_edit.setText("Capítulo")
    page._add_bookmark()
    page.tree.topLevelItem(0).setText(1, "9")
    monkeypatch.setattr(page.output_picker, "path", lambda: str(make_pdf("x.pdf", [(1, 1)]).with_name("o.pdf")))

    page._save()
    wait_for_tasks()

    assert any('A página "9" do marcador "Capítulo" não existe' in text for text in errors)
