"""Testes de ConvertOfficeToPDF (conversão própria em Python puro, sem LibreOffice)."""


import pytest
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pypdf import PdfReader

from core.office_convert import ConvertOfficeToPDF


def _make_docx(path):
    document = Document()
    document.add_heading("Título do documento", level=1)
    document.add_paragraph("Primeiro parágrafo de teste.")
    document.save(path)


def _make_xlsx(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dados"
    sheet.append(["Nome", "Valor"])
    sheet.append(["Item 1", 100])
    workbook.save(path)


def _make_pptx(path):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Título do slide"
    slide.placeholders[1].text_frame.text = "Conteúdo do slide de teste"
    presentation.save(path)


def _normalized_text(page) -> str:
    # O extract_text() do pypdf pode inserir espaços/quebras espúrias ao redor
    # de caracteres acentuados, mesmo quando o PDF renderiza corretamente
    # (confirmado visualmente durante o desenvolvimento, inclusive com o
    # LibreOffice fazendo a conversão de verdade). Normaliza espaços em
    # branco antes de comparar.
    return " ".join(page.extract_text().split())


def test_docx_to_pdf(tmp_path):
    docx_path = tmp_path / "doc.docx"
    _make_docx(docx_path)

    output_path = tmp_path / "doc.pdf"
    ConvertOfficeToPDF().run(str(docx_path), str(output_path))

    reader = PdfReader(str(output_path))
    text = _normalized_text(reader.pages[0])
    assert "Título do documento" in text
    assert "Primeiro" in text and "de teste." in text


def test_xlsx_to_pdf(tmp_path):
    xlsx_path = tmp_path / "planilha.xlsx"
    _make_xlsx(xlsx_path)

    output_path = tmp_path / "planilha.pdf"
    ConvertOfficeToPDF().run(str(xlsx_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert "Item 1" in _normalized_text(reader.pages[0])


def test_pptx_to_pdf(tmp_path):
    pptx_path = tmp_path / "apresentacao.pptx"
    _make_pptx(pptx_path)

    output_path = tmp_path / "apresentacao.pdf"
    ConvertOfficeToPDF().run(str(pptx_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 1
    assert "Título do slide" in _normalized_text(reader.pages[0])


def test_rejects_unsupported_format(tmp_path):
    bogus_path = tmp_path / "arquivo.txt"
    bogus_path.write_text("conteudo", encoding="utf-8")

    with pytest.raises(ValueError):
        ConvertOfficeToPDF().run(str(bogus_path), str(tmp_path / "out.pdf"))


def _all_text(path) -> str:
    return " ".join(_normalized_text(page) for page in PdfReader(str(path)).pages)


def test_docx_tables_are_converted_in_order(tmp_path):
    document = Document()
    document.add_paragraph("Antes da tabela")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Produto"
    table.cell(0, 1).text = "Preço"
    table.cell(1, 0).text = "Caneta"
    table.cell(1, 1).text = "R$ 2,50"
    document.add_paragraph("Depois da tabela")
    docx_path = tmp_path / "tabela.docx"
    document.save(docx_path)
    output_path = tmp_path / "tabela.pdf"

    ConvertOfficeToPDF().run(str(docx_path), str(output_path))

    text = _all_text(output_path)
    for expected in ("Produto", "Preço", "Caneta", "R$ 2,50"):
        assert expected in text
    assert text.index("Antes da tabela") < text.index("Caneta") < text.index("Depois da tabela")


def test_docx_images_and_headers_are_reported(tmp_path):
    from PIL import Image

    image_path = tmp_path / "logo.png"
    Image.new("RGB", (40, 40), "red").save(image_path)
    document = Document()
    document.sections[0].header.paragraphs[0].text = "Cabeçalho da empresa"
    document.add_paragraph("Texto")
    document.add_picture(str(image_path))
    docx_path = tmp_path / "imagem.docx"
    document.save(docx_path)

    result = ConvertOfficeToPDF().run(str(docx_path), str(tmp_path / "out.pdf"))

    assert any("imagens" in warning for warning in result.warnings)
    assert any("Cabeçalhos" in warning for warning in result.warnings)


def test_pptx_long_text_continues_on_the_next_page(tmp_path):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Muitos itens"
    frame = slide.placeholders[1].text_frame
    frame.text = "Item 1"
    for number in range(2, 41):
        frame.add_paragraph().text = f"Item {number}"
    pptx_path = tmp_path / "longo.pptx"
    presentation.save(pptx_path)
    output_path = tmp_path / "longo.pdf"

    result = ConvertOfficeToPDF().run(str(pptx_path), str(output_path))

    text = _all_text(output_path)
    assert all(f"Item {number}" in text for number in range(1, 41))  # antes, 14 de 40 sumiam
    assert len(PdfReader(str(output_path)).pages) > 1
    assert any("continuaram" in warning for warning in result.warnings)


def test_pptx_tables_are_included(tmp_path):
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Resultados"
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(6), Inches(1)).table
    table.cell(0, 0).text = "Trimestre"
    table.cell(1, 0).text = "Q1"
    table.cell(1, 1).text = "42"
    pptx_path = tmp_path / "tabela.pptx"
    presentation.save(pptx_path)
    output_path = tmp_path / "tabela.pdf"

    ConvertOfficeToPDF().run(str(pptx_path), str(output_path))

    text = _all_text(output_path)
    assert "Trimestre" in text and "Q1" in text and "42" in text


@pytest.mark.parametrize("suffix", [".xls", ".doc", ".odt"])
def test_formats_that_needed_libreoffice_are_rejected(tmp_path, suffix):
    path = tmp_path / f"antigo{suffix}"
    path.write_bytes(b"qualquer coisa")

    with pytest.raises(ValueError, match="Formato não suportado"):
        ConvertOfficeToPDF().run(str(path), str(tmp_path / "out.pdf"))
