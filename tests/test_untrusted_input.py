"""PDF e documentos de entrada como não confiáveis (M30): página gigante, zip bomb do Office e
ciclos nas árvores de nomes."""

import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject

import core.base
from core.base import add_object, open_pdfium, render_scale


def _blank(path, size=(200, 200)):
    writer = PdfWriter()
    writer.add_blank_page(*size)
    writer.write(str(path))
    return path


def test_render_scale_caps_the_pixels_of_a_giant_page(tmp_path, monkeypatch):
    document = open_pdfium(str(_blank(tmp_path / "gigante.pdf", (14400, 14400))))  # o máximo do formato
    try:
        page = document[0]
        capped = render_scale(page, 300 / 72)
        assert 14400 * capped * 14400 * capped == pytest.approx(core.base.MAX_RENDER_PIXELS, rel=1e-6)
        small = open_pdfium(str(_blank(tmp_path / "a4.pdf", (595, 842))))
        assert render_scale(small[0], 300 / 72) == 300 / 72  # A4 a 300 DPI passa inteiro
        small.close()
    finally:
        document.close()


def test_conversion_and_viewer_use_the_cap(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from core.convert import ConvertToImages
    from ui.viewer.render import logical_size, render_page

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(core.base, "MAX_RENDER_PIXELS", 10_000)  # 100 x 100
    source = _blank(tmp_path / "doc.pdf")

    (image_path,) = ConvertToImages().run(str(source), str(tmp_path / "out"), scale=2)
    from PIL import Image

    with Image.open(image_path) as image:
        assert image.size == (100, 100) and round(image.info["dpi"][0]) == 36  # a resolução de verdade

    document = open_pdfium(str(source))
    try:
        pixmap = render_page(document[0], 2.0, device_pixel_ratio=2.0)
    finally:
        document.close()
    assert (pixmap.width(), pixmap.height()) == (100, 100)
    assert (logical_size(pixmap).width(), logical_size(pixmap).height()) == (400, 400)  # o mesmo tamanho na tela


def _zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_an_office_zip_bomb_is_refused_before_opening(tmp_path, monkeypatch):
    import core.office_convert
    from core.office_convert import ConvertOfficeToPDF

    monkeypatch.setattr(core.office_convert, "_MAX_UNPACKED_BYTES", 1_000_000)
    bomb = _zip(tmp_path / "bomba.docx", {"word/document.xml": b"0" * 5_000_000})  # 5 MB em poucos KB
    assert bomb.stat().st_size < 50_000

    with pytest.raises(ValueError, match="descompacta para mais de 0 MB"):
        ConvertOfficeToPDF().run(str(bomb), str(tmp_path / "out.pdf"))
    assert not (tmp_path / "out.pdf").exists()


def test_a_file_that_is_not_a_zip_gets_a_clear_message(tmp_path):
    from core.form_fields import ImportFormDataCSV
    from core.office_convert import ConvertOfficeToPDF

    fake = tmp_path / "planilha.xlsx"
    fake.write_bytes(b"isto nao e um zip")

    with pytest.raises(ValueError, match="não é um documento do Office válido"):
        ConvertOfficeToPDF().run(str(fake), str(tmp_path / "out.pdf"))
    with pytest.raises(ValueError, match="não é um documento do Office válido"):
        ImportFormDataCSV().run(str(_blank(tmp_path / "f.pdf")), str(tmp_path / "o.pdf"), str(fake))


def _cyclic_name_trees(path):
    """Anexos e destinos nomeados em árvores cujo /Kids aponta para elas mesmas."""
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.add_attachment("nota.txt", b"conteudo")
    names = writer.root_object["/Names"].get_object()
    files = add_object(writer, names["/EmbeddedFiles"].get_object())
    names[NameObject("/EmbeddedFiles")] = files
    files.get_object()[NameObject("/Kids")] = ArrayObject([files])
    writer.add_named_destination("inicio", 0)
    dests = add_object(writer, names["/Dests"].get_object())
    names[NameObject("/Dests")] = dests
    dests.get_object()[NameObject("/Kids")] = ArrayObject([dests])
    writer.write(str(path))
    return path


def test_cyclic_name_trees_do_not_hang(tmp_path):
    from core.attachments import ListAttachments
    from core.document import iter_name_tree

    path = _cyclic_name_trees(tmp_path / "ciclo.pdf")
    reader = PdfReader(str(path))

    names = reader.root_object["/Names"]
    assert [str(key) for key, _value in iter_name_tree(names.raw_get("/EmbeddedFiles"))] == ["nota.txt"]
    assert [info.name for info in ListAttachments().run(str(path))] == ["nota.txt"]
    assert reader.named_destinations == {}  # o pypdf vê o ciclo e desiste da árvore, sem travar
