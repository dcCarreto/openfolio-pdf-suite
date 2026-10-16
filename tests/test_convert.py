from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from core.convert import ConvertFromImages, ConvertToImages


def test_convert_to_images_creates_one_image_per_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (300, 300)])
    output_dir = tmp_path / "out"

    output_paths = ConvertToImages().run(str(pdf_path), str(output_dir))

    assert len(output_paths) == 2
    for path in output_paths:
        assert Path(path).exists()


def test_convert_from_images_creates_multi_page_pdf(tmp_path):
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    image_paths = []
    for index, color in enumerate(colors):
        path = tmp_path / f"img{index}.png"
        Image.new("RGB", (100, 100), color=color).save(path)
        image_paths.append(str(path))

    output_path = tmp_path / "out.pdf"
    ConvertFromImages().run(image_paths, str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == len(colors)


def test_convert_from_images_with_empty_list_raises(tmp_path):
    output_path = tmp_path / "out.pdf"

    with pytest.raises(ValueError):
        ConvertFromImages().run([], str(output_path))


def _image_box(pdf_path, page_index=0):
    """Tamanho da página e retângulo (em pontos) em que a imagem foi desenhada."""
    page = PdfReader(str(pdf_path)).pages[page_index]
    matrices = []

    def visitor(operator, operands, cm, tm):
        if operator == b"Do":
            matrices.append(cm)

    page.extract_text(visitor_operand_before=visitor)
    a, _b, _c, d, e, f = matrices[0]
    return (float(page.mediabox.width), float(page.mediabox.height)), (e, f, e + a, f + d)


def test_transparent_png_gets_a_white_background(tmp_path):
    image_path = tmp_path / "transparente.png"
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(image_path)
    output_path = tmp_path / "out.pdf"

    ConvertFromImages().run([str(image_path)], str(output_path))

    (image,) = PdfReader(str(output_path)).pages[0].images
    assert image.image.convert("RGB").getpixel((50, 50)) == (255, 255, 255)


def test_photo_fits_an_a4_page_instead_of_a_giant_one(tmp_path):
    image_path = tmp_path / "foto.jpg"
    Image.new("RGB", (4000, 3000), "red").save(image_path)
    output_path = tmp_path / "out.pdf"

    ConvertFromImages().run([str(image_path)], str(output_path), page_size="A4", margin_mm=10)

    (page_width, page_height), (left, bottom, right, top) = _image_box(output_path)
    assert (round(page_width), round(page_height)) == (842, 595)  # paisagem
    assert left >= 28 and bottom >= 28 and right <= page_width - 28 and top <= page_height - 28
    assert abs((right - left) / (top - bottom) - 4 / 3) < 0.01  # sem distorcer


def test_fit_to_image_uses_the_dpi(tmp_path):
    image_path = tmp_path / "scan.png"
    Image.new("L", (2480, 3508), 255).save(image_path)
    output_path = tmp_path / "out.pdf"

    ConvertFromImages().run([str(image_path)], str(output_path), page_size="fit", dpi=300)

    (page_width, page_height), _box = _image_box(output_path)
    assert (round(page_width), round(page_height)) == (595, 842)  # 2480x3508 a 300 DPI = A4


def test_exif_orientation_is_applied(tmp_path):
    image_path = tmp_path / "celular.jpg"
    image = Image.new("RGB", (400, 200), "blue")
    exif = image.getexif()
    exif[0x0112] = 6  # câmera deitada: girar 90 graus para exibir
    image.save(image_path, exif=exif)
    output_path = tmp_path / "out.pdf"

    ConvertFromImages().run([str(image_path)], str(output_path), page_size="fit", dpi=72)

    (page_width, page_height), _box = _image_box(output_path)
    assert (round(page_width), round(page_height)) == (200, 400)


def test_plain_jpeg_is_embedded_without_recompression(tmp_path):
    image_path = tmp_path / "foto.jpg"
    Image.effect_noise((600, 400), 50).convert("RGB").save(image_path, quality=80)
    output_path = tmp_path / "out.pdf"

    ConvertFromImages().run([str(image_path)], str(output_path))

    xobjects = PdfReader(str(output_path)).pages[0]["/Resources"]["/XObject"]
    (image,) = [xobjects[name].get_object() for name in xobjects]
    assert image["/Filter"] == ["/DCTDecode"]
    assert image._data == image_path.read_bytes()


def test_invalid_page_size_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Tamanho de página"):
        ConvertFromImages().run(["x.png"], str(tmp_path / "out.pdf"), page_size="A0")
