"""Comparação lado a lado (A10): diff de texto do documento inteiro com a posição das
palavras, e a janela com as duas versões, os destaques e a rolagem sincronizada."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from PySide6.QtWidgets import QApplication, QPushButton
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate

from core.compare import CompareDocuments, CompareText
from ui.document_session import DocumentSession
from ui.pages.compare_page import ComparePage
from ui.tasks import wait_for_tasks

_WORDS = "o contrato de prestação de serviços que as partes assinam vale por um ano e se renova".split()
_NEW_PARAGRAPH = (
    "Cláusula nova incluída só na segunda versão, com duas linhas, que empurra todo o texto "
    "seguinte para a frente e para as páginas seguintes."
)


def _paragraphs() -> list[str]:
    return [f"Parágrafo {n}: " + " ".join(_WORDS[(n + k) % len(_WORDS)] for k in range(70)) for n in range(30)]


def _header_and_footer(canvas, document):
    canvas.drawString(72, A4[1] - 40, "Contrato de prestação de serviços — minuta")
    canvas.drawString(A4[0] / 2, 30, f"Página {document.page}")


def _build(path, paragraphs):
    style = getSampleStyleSheet()["BodyText"]
    SimpleDocTemplate(str(path), pagesize=A4).build(
        [Paragraph(text, style) for text in paragraphs], onFirstPage=_header_and_footer, onLaterPages=_header_and_footer
    )


@pytest.fixture
def versions(tmp_path):
    """A e B: B tem um parágrafo a mais no começo, "100" virou "200" e um "não" a mais."""
    paragraphs = _paragraphs()
    paragraphs[20] = paragraphs[20].replace("Parágrafo 20:", "Parágrafo 20: valor 100;")
    _build(tmp_path / "a.pdf", paragraphs)
    changed = list(paragraphs)
    changed.insert(1, _NEW_PARAGRAPH)
    changed[21] = changed[21].replace("valor 100", "valor 200")
    changed[26] = changed[26].replace("que as partes", "que as partes não", 1)
    _build(tmp_path / "b.pdf", changed)
    return tmp_path / "a.pdf", tmp_path / "b.pdf"


def _text_box(path, page_index, text):
    """A caixa do texto na página, pela busca do pdfium."""
    document = pdfium.PdfDocument(str(path))
    try:
        textpage = document[page_index].get_textpage()
        searcher = textpage.search(text, match_case=True, match_whole_word=True)
        start, count = searcher.get_next()
        boxes = [textpage.get_charbox(start + offset) for offset in range(count)]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    finally:
        document.close()


def test_text_that_only_moved_to_another_page_is_not_a_difference(versions):
    path_a, path_b = versions

    diff = CompareDocuments().run(str(path_a), str(path_b))

    # Página a página, o parágrafo incluído "muda" quase todas as páginas; no documento
    # inteiro, só sobram as três mudanças de verdade. O cabeçalho e o número da página, que
    # caem em outro ponto do texto depois que ele escorre, ficam de fora.
    assert sum(result.changed for result in CompareText().run(str(path_a), str(path_b))) >= 3
    assert [(change.kind, change.text_a, change.text_b) for change in diff.changes] == [
        ("added", "", _NEW_PARAGRAPH),
        ("changed", "100;", "200;"),
        ("added", "", "não"),
    ]
    added = diff.changes[0]
    assert added.boxes_a == [] and added.anchor_a.page == 0  # em A, onde o parágrafo entraria
    assert len(added.boxes_b) == 2 and {box.page for box in added.boxes_b} == {0}  # uma caixa por linha
    changed = diff.changes[1]
    assert changed.anchor_a.page != changed.anchor_b.page or changed.anchor_a.top != changed.anchor_b.top
    assert changed.boxes_b == [changed.anchor_b]
    assert changed.anchor_b[1:] == pytest.approx(_text_box(path_b, changed.anchor_b.page, "200;"))
    assert diff.matches and diff.pages_without_text_a == [] and diff.pages_without_text_b == []


def test_header_and_footer_filter_keeps_text_that_only_looks_repeated(tmp_path):
    # Título de cláusula no topo de toda página, na mesma altura: não é cabeçalho, e mudar o
    # número dele é diferença. Já o rodapé "Página N de 4" sai.
    for name, third in (("a.pdf", "3ª"), ("b.pdf", "9ª")):
        canvas = rl_canvas.Canvas(str(tmp_path / name), pagesize=A4)
        for number in range(1, 5):
            canvas.drawString(72, 780, f"Cláusula {third if number == 3 else f'{number}ª'}")
            canvas.drawString(72, 700, f"Texto próprio da cláusula número {number}.")
            canvas.drawString(250, 30, f"Página {number} de 4")
            canvas.showPage()
        canvas.save()

    diff = CompareDocuments().run(str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf"))

    assert [(change.text_a, change.text_b) for change in diff.changes] == [("3ª", "9ª")]
    assert not any(box_a.bottom < 40 for box_a, _box_b in diff.matches)  # o rodapé ficou de fora


def test_text_outside_the_visible_page_is_ignored(tmp_path):
    # O Qt repete, acima do topo da página seguinte, a linha de tabela que passa de página.
    for name, hidden in (("a.pdf", True), ("b.pdf", False)):
        canvas = rl_canvas.Canvas(str(tmp_path / name), pagesize=(300, 200))
        canvas.drawString(20, 100, "Texto visível")
        if hidden:
            canvas.drawString(20, 205, "linha repetida fora da página")
        canvas.save()

    diff = CompareDocuments().run(str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf"))

    assert diff.changes == [] and len(diff.matches) == 1


def test_pages_without_text_are_reported(versions, tmp_path):
    path_a, path_b = versions
    writer = PdfWriter(clone_from=str(path_b))
    writer.add_blank_page()
    writer.write(tmp_path / "escaneado.pdf")

    diff = CompareDocuments().run(str(path_a), str(tmp_path / "escaneado.pdf"))

    assert diff.pages_without_text_b == [len(writer.pages) - 1]


def test_side_by_side_window_highlights_navigates_and_syncs_scrolling(versions):
    app = QApplication.instance() or QApplication([])
    path_a, path_b = versions
    session = DocumentSession()
    session.open(str(path_a))
    page = ComparePage(session)
    page.side_b_picker._path = str(path_b)

    next(button for button in page.stack.widget(0).findChildren(QPushButton) if button.text() == "Comparar lado a lado").click()
    wait_for_tasks()
    window = page.compare_window
    window.resize(1400, 900)
    window.show()
    for _ in range(5):
        app.processEvents()

    assert window.changes_list.count() == 3
    assert window.changes_list.item(1).text().startswith("Pág. ") and "“100;” → “200;”" in window.changes_list.item(1).text()
    assert window.changes_list.currentRow() == 0  # já abre na primeira diferença

    window.go_to_change(1)
    app.processEvents()
    change = window.diff.changes[1]
    assert window.counter_label.text() == "2 de 3"
    assert window.pane_a.center_y() == pytest.approx(window.pane_a.y_of(change.anchor_a), abs=2)
    assert window.pane_b.center_y() == pytest.approx(window.pane_b.y_of(change.anchor_b), abs=2)

    # O destaque está pintado na página, no lugar da palavra.
    box = change.anchor_b
    pane = window.pane_b
    point = pane._screen_rect(box).center().toPoint()
    color = pane._labels[box.page].pixmap().toImage().pixelColor(point)
    assert color.red() > color.blue() + 40  # laranja ("alterado") sobre o papel

    # Rolar A leva B ao trecho correspondente, que está mais abaixo (o parágrafo incluído).
    box_a, box_b = window.diff.matches[len(window.diff.matches) // 2]
    window.pane_a.scroll_center_to(window.pane_a.y_of(box_a))
    app.processEvents()
    assert window.pane_b.center_y() == pytest.approx(window.pane_b.y_of(box_b), abs=2)
    assert window.pane_b.center_y() > window.pane_a.center_y()

    window.close()
    app.processEvents()
