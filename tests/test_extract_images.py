import pytest
from PIL import Image
from pypdf import PdfReader

from core.base import EncryptedPDFError
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
