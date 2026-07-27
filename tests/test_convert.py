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
