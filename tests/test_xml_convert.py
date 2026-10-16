from pypdf import PdfReader

from core.xml_convert import ConvertXMLToPDF


def test_convert_xml_to_pdf(tmp_path):
    xml_path = tmp_path / "dados.xml"
    xml_path.write_text("<root><item nome='Teste'>Conteudo do item</item></root>", encoding="utf-8")

    output_path = tmp_path / "dados.pdf"
    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "item" in text
    assert "Conteudo do item" in text


def test_convert_invalid_xml_falls_back_to_raw_text(tmp_path):
    xml_path = tmp_path / "invalido.xml"
    xml_path.write_text("isso nao e um xml valido <<<", encoding="utf-8")

    output_path = tmp_path / "invalido.pdf"
    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) >= 1


def test_convert_xml_with_non_utf8_encoding_does_not_crash(tmp_path):
    xml_path = tmp_path / "latin1.xml"
    xml_path.write_bytes("<root>café com ção</root>".encode("latin-1"))

    output_path = tmp_path / "latin1.pdf"
    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) >= 1


def _char_boxes(pdf_path):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[0]
        width = page.get_width()
        textpage = page.get_textpage()
        boxes = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
        text = textpage.get_text_range()
        textpage.close()
    finally:
        document.close()
    return width, boxes, text


def test_long_lines_are_wrapped_inside_the_page(tmp_path):
    long_value = " ".join(f"palavra{i}" for i in range(60))
    xml_path = tmp_path / "longo.xml"
    xml_path.write_text(f"<root><item>{long_value}</item><fim>ultimo</fim></root>", encoding="utf-8")
    output_path = tmp_path / "longo.pdf"

    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    width, boxes, text = _char_boxes(output_path)
    assert max(box[2] for box in boxes) <= width - 30  # nada passa da margem direita
    assert "palavra59" in text and "ultimo" in text  # nada foi cortado


def test_wrapped_lines_keep_the_indentation():
    from core.xml_convert import wrap_code_line

    pieces = wrap_code_line("    <item>" + "x" * 30 + " " + "y" * 30 + "</item>", 40)

    assert len(pieces) > 1
    assert all(len(piece) <= 40 for piece in pieces)
    assert all(piece.startswith("        ") for piece in pieces[1:])


def test_declared_encoding_is_respected(tmp_path):
    xml_path = tmp_path / "declarado.xml"
    xml_path.write_bytes('<?xml version="1.0" encoding="ISO-8859-1"?><root>ação</root>'.encode("latin-1"))
    output_path = tmp_path / "declarado.pdf"

    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    assert "ação" in PdfReader(str(output_path)).pages[0].extract_text()


def test_characters_outside_latin1_are_kept(tmp_path):
    xml_path = tmp_path / "unicode.xml"
    xml_path.write_text("<root>Łódź Ωμέγα €</root>", encoding="utf-8")
    output_path = tmp_path / "unicode.pdf"

    ConvertXMLToPDF().run(str(xml_path), str(output_path))

    assert "Łódź Ωμέγα €" in PdfReader(str(output_path)).pages[0].extract_text()


def test_landscape_pages(tmp_path):
    xml_path = tmp_path / "dados.xml"
    xml_path.write_text("<root/>", encoding="utf-8")
    output_path = tmp_path / "dados.pdf"

    ConvertXMLToPDF().run(str(xml_path), str(output_path), landscape_pages=True)

    page = PdfReader(str(output_path)).pages[0]
    assert page.mediabox.width > page.mediabox.height
