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


def test_header_footer_rejects_unbalanced_brace_with_clear_error(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError, match="chave literal"):
        AddHeaderFooter().run(str(pdf_path), str(tmp_path / "out.pdf"), text="valor { solto")
