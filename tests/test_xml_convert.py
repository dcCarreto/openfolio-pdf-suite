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
