import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.page_numbers import AddBatesNumbers, AddHeaderFooter, AddPageNumbers


def test_add_page_numbers_starting_value(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300), (300, 300)])
    output_path = tmp_path / "numbered.pdf"

    AddPageNumbers().run(str(pdf_path), str(output_path), start_at=5)

    reader = PdfReader(str(output_path))
    texts = [page.extract_text() for page in reader.pages]
    assert "5" in texts[0]
    assert "6" in texts[1]
    assert "7" in texts[2]


def test_add_page_numbers_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddPageNumbers().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_add_bates_numbers_uses_prefix_and_padding(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300), (300, 300)])
    output_path = tmp_path / "bates.pdf"

    AddBatesNumbers().run(str(pdf_path), str(output_path), prefix="CASO-", start_at=1, digits=4)

    reader = PdfReader(str(output_path))
    texts = [page.extract_text() for page in reader.pages]
    assert "CASO-0001" in texts[0]
    assert "CASO-0002" in texts[1]
    assert "CASO-0003" in texts[2]


def test_add_bates_numbers_respects_start_at(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "bates.pdf"

    AddBatesNumbers().run(str(pdf_path), str(output_path), start_at=100, digits=3)

    reader = PdfReader(str(output_path))
    assert "100" in reader.pages[0].extract_text()


def test_add_bates_numbers_rejects_invalid_position(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        AddBatesNumbers().run(str(pdf_path), str(tmp_path / "out.pdf"), position="middle")


def test_add_bates_numbers_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddBatesNumbers().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_add_header_footer_resolves_placeholders_per_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300)])
    output_path = tmp_path / "out.pdf"

    AddHeaderFooter().run(str(pdf_path), str(output_path), text="Página {page} de {pages}")

    reader = PdfReader(str(output_path))
    assert "Página 1 de 2" in reader.pages[0].extract_text()
    assert "Página 2 de 2" in reader.pages[1].extract_text()


def test_add_header_footer_supports_all_positions(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    for position in ("header-left", "header-center", "header-right", "footer-left", "footer-center", "footer-right"):
        output_path = tmp_path / f"out_{position}.pdf"
        AddHeaderFooter().run(str(pdf_path), str(output_path), text="Confidencial", position=position)
        assert "Confidencial" in PdfReader(str(output_path)).pages[0].extract_text()


def test_add_header_footer_rejects_invalid_position(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        AddHeaderFooter().run(str(pdf_path), str(tmp_path / "out.pdf"), text="x", position="middle")


def test_add_header_footer_rejects_invalid_placeholder(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        AddHeaderFooter().run(str(pdf_path), str(tmp_path / "out.pdf"), text="{nao_existe}")


def test_add_header_footer_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddHeaderFooter().run(str(encrypted_path), str(tmp_path / "out.pdf"), text="x")


def _visual_text_box(path, text):
    import pypdfium2 as pdfium

    from core.geometry import PageGeometry

    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        geometry = PageGeometry.from_pdfium_page(page)
        textpage = page.get_textpage()
        searcher = textpage.search(text)
        index, count = searcher.get_next()
        boxes = [textpage.get_charbox(i) for i in range(index, index + count)]
        searcher.close()
        textpage.close()
    finally:
        document.close()
    user = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return geometry, geometry.user_rect_to_visual(user)


@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_page_number_stays_at_the_bottom_center_on_rotated_pages(make_text_pdf, tmp_path, rotate):
    pdf_path = make_text_pdf(f"rot{rotate}.pdf", [(80, 650, "conteudo")], rotate=rotate)
    output_path = tmp_path / "numbered.pdf"

    AddPageNumbers().run(str(pdf_path), str(output_path), start_at=7)

    geometry, (left, bottom, right, top) = _visual_text_box(output_path, "7")
    assert abs((left + right) / 2 - geometry.width / 2) < 10  # centralizado na tela
    assert bottom < 40  # no rodapé da tela
    assert right - left < 20 and top - bottom < 20


def test_bates_goes_to_the_visual_corner_on_rotated_pages(make_text_pdf, tmp_path):
    pdf_path = make_text_pdf("rot.pdf", [(80, 650, "conteudo")], rotate=90)
    output_path = tmp_path / "bates.pdf"

    AddBatesNumbers().run(str(pdf_path), str(output_path), prefix="CASO-", digits=3, position="top-left")

    geometry, (left, bottom, right, top) = _visual_text_box(output_path, "CASO-001")
    assert left < 40 and top > geometry.height - 40
    assert right - left > top - bottom  # de pé, lido na horizontal


def test_header_footer_accepts_escaped_braces(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    AddHeaderFooter().run(str(pdf_path), str(output_path), text="{{rascunho}} pag {page}")

    assert "{rascunho} pag 1" in PdfReader(str(output_path)).pages[0].extract_text()


def test_header_footer_keeps_lone_braces_as_text(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    AddHeaderFooter().run(str(pdf_path), str(output_path), text="valor { solto } de {pages}")

    assert "valor { solto } de 1" in PdfReader(str(output_path)).pages[0].extract_text()


def test_header_footer_names_the_unknown_placeholder(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError, match=r"\{pagina\}"):
        AddHeaderFooter().run(str(pdf_path), str(tmp_path / "out.pdf"), text="Página {pagina}")


def test_overlay_text_outside_latin1_is_kept(make_pdf, tmp_path):
    # Fonte embutida (core/fonts.py): antes, com a Helvetica base14, "Ł", "ő" e "Ω" sumiam.
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    AddHeaderFooter().run(str(pdf_path), str(output_path), text="Łódź ő Ω {page}")

    assert "Łódź ő Ω 1" in PdfReader(str(output_path)).pages[0].extract_text()


def _texts(path) -> list[str]:
    return [page.extract_text().strip() for page in PdfReader(str(path)).pages]


def test_roman_numerals_skip_the_cover(make_pdf, tmp_path):
    output_path = tmp_path / "out.pdf"
    AddPageNumbers().run(str(make_pdf("doc.pdf", [(300, 300)] * 5)), str(output_path), style="roman", skip_first=1)

    assert _texts(output_path) == ["", "i", "ii", "iii", "iv"]


def test_to_roman():
    from core.page_numbers import to_roman

    assert [to_roman(n) for n in (1, 4, 9, 14, 40, 90, 400, 1994, 3999)] == [
        "I", "IV", "IX", "XIV", "XL", "XC", "CD", "MCMXCIV", "MMMCMXCIX"
    ]  # fmt: skip
    with pytest.raises(ValueError):
        to_roman(0)


def test_only_the_chosen_pages_are_numbered_in_sequence(make_pdf, tmp_path):
    output_path = tmp_path / "out.pdf"
    AddPageNumbers().run(str(make_pdf("doc.pdf", [(300, 300)] * 5)), str(output_path), style="ROMAN", pages=[4, 1, 2])

    assert _texts(output_path) == ["", "I", "II", "", "III"]


def test_page_labels_are_written_as_they_are(make_pdf, tmp_path):
    from pypdf import PdfWriter
    from pypdf.constants import PageLabelStyle

    writer = PdfWriter(clone_from=str(make_pdf("doc.pdf", [(300, 300)] * 4)))
    writer.set_page_label(0, 1, style=PageLabelStyle.LOWERCASE_ROMAN)
    writer.set_page_label(2, 3, style=PageLabelStyle.DECIMAL, prefix="A-")
    labelled = tmp_path / "rotulos.pdf"
    writer.write(labelled)
    output_path = tmp_path / "out.pdf"

    AddPageNumbers().run(str(labelled), str(output_path), use_page_labels=True, skip_first=1)

    assert _texts(output_path) == ["", "ii", "A-1", "A-2"]


def test_position_and_font_of_the_page_number(make_text_pdf, tmp_path):
    pdf_path = make_text_pdf("doc.pdf", [])
    output_path = tmp_path / "out.pdf"
    AddPageNumbers().run(str(pdf_path), str(output_path), position="header-right", font="OpenFolioMono")

    geometry, (left, bottom, right, top) = _visual_text_box(output_path, "1")
    assert right > geometry.width - 40 and top > geometry.height - 40
    fonts = PdfReader(str(output_path)).pages[0]["/Resources"]["/Font"]
    assert any("Mono" in str(fonts[name].get_object()["/BaseFont"]) for name in fonts)


def test_skipping_every_page_is_an_error(make_pdf, tmp_path):
    with pytest.raises(ValueError, match="Nenhuma página"):
        AddPageNumbers().run(str(make_pdf("doc.pdf", [(300, 300)] * 2)), str(tmp_path / "out.pdf"), skip_first=2)


def test_page_numbers_tab_numbers_the_selected_pages(make_pdf, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.document_session import DocumentSession
    from ui.pages.page_numbers_page import PageNumbersPage
    from ui.tasks import wait_for_tasks

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    session = DocumentSession()
    session.open(str(make_pdf("doc.pdf", [(300, 300)] * 4)))
    session.set_selected_pages([1, 3])
    page = PageNumbersPage(session)
    output_path = tmp_path / "numerado.pdf"
    monkeypatch.setattr(page.output_picker, "path", lambda: str(output_path))

    page.number_style_combo.setCurrentIndex(page.number_style_combo.findData("roman"))
    page.number_selection_button.click()
    page._apply()
    assert wait_for_tasks()

    assert _texts(output_path) == ["", "i", "", "ii"]
    page.page_labels_check.setChecked(True)
    assert not page.number_style_combo.isEnabled() and not page.start_at_spin.isEnabled()
