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
