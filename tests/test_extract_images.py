import pytest
from PIL import Image
from pypdf import PdfReader

from core.base import EncryptedPDFError, add_object
from core.convert import ConvertFromImages
from core.extract_images import ExtractImages, ListEmbeddedImages, ReplaceEmbeddedImage


def test_extract_images_from_pdf(tmp_path):
    image_path = tmp_path / "photo.png"
    Image.new("RGB", (64, 64), color=(10, 20, 30)).save(image_path)

    pdf_path = tmp_path / "doc.pdf"
    ConvertFromImages().run([str(image_path)], str(pdf_path))

    output_dir = tmp_path / "extracted"
    output_paths = ExtractImages().run(str(pdf_path), str(output_dir))

    assert len(output_paths) == 1
    extracted = Image.open(output_paths[0])
    assert extracted.size == (64, 64)


def test_extract_images_returns_empty_list_when_no_images(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_dir = tmp_path / "extracted"

    output_paths = ExtractImages().run(str(pdf_path), str(output_dir))

    assert output_paths == []


def test_extract_images_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ExtractImages().run(str(encrypted_path), str(tmp_path / "extracted"))


def _pdf_with_one_image(tmp_path, size=(64, 64), color=(10, 20, 30)) -> str:
    image_path = tmp_path / "photo.png"
    Image.new("RGB", size, color=color).save(image_path)
    pdf_path = tmp_path / "doc.pdf"
    ConvertFromImages().run([str(image_path)], str(pdf_path))
    return str(pdf_path)


def test_list_embedded_images(tmp_path):
    pdf_path = _pdf_with_one_image(tmp_path, size=(64, 48))

    images = ListEmbeddedImages().run(pdf_path)

    assert len(images) == 1
    assert images[0].page_index == 0
    assert images[0].image_index == 0
    assert images[0].width == 64
    assert images[0].height == 48


def test_list_embedded_images_empty_for_pdf_without_images(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])

    assert ListEmbeddedImages().run(str(pdf_path)) == []


def test_replace_embedded_image(tmp_path):
    pdf_path = _pdf_with_one_image(tmp_path, color=(10, 20, 30))
    new_image_path = tmp_path / "new.png"
    Image.new("RGB", (64, 64), color=(200, 0, 0)).save(new_image_path)
    output_path = tmp_path / "out.pdf"

    ReplaceEmbeddedImage().run(
        pdf_path, str(output_path), page_number=0, image_index=0, new_image_path=str(new_image_path)
    )

    extracted = PdfReader(str(output_path)).pages[0].images[0].image
    assert extracted.convert("RGB").getpixel((0, 0)) == (200, 0, 0)


def test_replace_embedded_image_rejects_invalid_index(tmp_path):
    pdf_path = _pdf_with_one_image(tmp_path)
    new_image_path = tmp_path / "new.png"
    Image.new("RGB", (64, 64)).save(new_image_path)

    with pytest.raises(ValueError):
        ReplaceEmbeddedImage().run(
            pdf_path, str(tmp_path / "out.pdf"), page_number=0, image_index=5, new_image_path=str(new_image_path)
        )


def test_replace_embedded_image_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    new_image_path = tmp_path / "new.png"
    Image.new("RGB", (64, 64)).save(new_image_path)

    with pytest.raises(EncryptedPDFError):
        ReplaceEmbeddedImage().run(
            str(encrypted_path), str(tmp_path / "out.pdf"), page_number=0, image_index=0, new_image_path=str(new_image_path)
        )


def _drawn_box(pdf_path, page_index=0):
    page = PdfReader(str(pdf_path)).pages[page_index]
    matrices = []
    page.extract_text(visitor_operand_before=lambda op, args, cm, tm: matrices.append(cm) if op == b"Do" else None)
    a, _b, _c, d, e, f = matrices[0]
    return e, f, a, d


def test_replacement_with_another_proportion_is_not_distorted(tmp_path):
    pdf_path = _pdf_with_one_image(tmp_path, size=(200, 100))  # área 2:1
    new_image_path = tmp_path / "quadrada.png"
    Image.new("RGB", (80, 80), color=(0, 0, 255)).save(new_image_path)
    output_path = tmp_path / "out.pdf"

    ReplaceEmbeddedImage().run(pdf_path, str(output_path), page_number=0, image_index=0, new_image_path=str(new_image_path))

    image = PdfReader(str(output_path)).pages[0].images[0].image.convert("RGBA")
    assert abs(image.width / image.height - 2) < 0.05  # a imagem nova ocupa a área sem esticar
    assert image.getpixel((image.width // 2, image.height // 2))[:3] == (0, 0, 255)
    assert image.getpixel((2, image.height // 2))[3] == 0  # sobra transparente nas laterais
    assert _drawn_box(output_path) == _drawn_box(pdf_path)  # mesma posição e tamanho na página


def test_stretch_mode_fills_the_area(tmp_path):
    pdf_path = _pdf_with_one_image(tmp_path, size=(200, 100))
    new_image_path = tmp_path / "quadrada.png"
    Image.new("RGB", (80, 80), color=(0, 0, 255)).save(new_image_path)
    output_path = tmp_path / "out.pdf"

    ReplaceEmbeddedImage().run(
        pdf_path, str(output_path), page_number=0, image_index=0, new_image_path=str(new_image_path), fit="stretch"
    )

    image = PdfReader(str(output_path)).pages[0].images[0].image
    assert image.size == (80, 80)


def test_replacing_an_image_shared_by_other_pages_reports_them(tmp_path):
    from pypdf import PdfWriter

    from pypdf.generic import NameObject

    single = _pdf_with_one_image(tmp_path)
    writer = PdfWriter(clone_from=single)
    first = writer.pages[0]
    second = writer.add_blank_page(width=float(first.mediabox.width), height=float(first.mediabox.height))
    second[NameObject("/Resources")] = first.raw_get("/Resources")  # a mesma imagem (mesmo objeto)
    second[NameObject("/Contents")] = first.raw_get("/Contents")
    shared = tmp_path / "shared.pdf"
    writer.write(str(shared))
    new_image_path = tmp_path / "nova.png"
    Image.new("RGB", (64, 64), color=(0, 200, 0)).save(new_image_path)

    result = ReplaceEmbeddedImage().run(
        str(shared), str(tmp_path / "out.pdf"), page_number=0, image_index=0, new_image_path=str(new_image_path)
    )

    assert result.other_pages == [1]


def test_inline_image_has_a_clear_error(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    content = DecodedStreamObject()
    content.set_data(b"q 50 0 0 50 0 0 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI Q")
    page[NameObject("/Contents")] = add_object(writer, content)
    pdf_path = tmp_path / "inline.pdf"
    writer.write(str(pdf_path))
    new_image_path = tmp_path / "nova.png"
    Image.new("RGB", (4, 4)).save(new_image_path)

    with pytest.raises(ValueError, match="inline"):
        ReplaceEmbeddedImage().run(
            str(pdf_path), str(tmp_path / "out.pdf"), page_number=0, image_index=0, new_image_path=str(new_image_path)
        )
