from PIL import Image

from core.convert import ConvertFromImages
from core.extract_images import ExtractImages


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
