"""Compressão de imagens (B18): níveis, DPI efetivo, transparência e o caso "não ficou menor"."""

import io
import os

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

import core.compress as compress
from core.compress import CompressPDF
from core.progress import OperationCancelled, Progress


def _scan_like_image(size=(1200, 1650), color=False) -> Image.Image:
    """Uma "página escaneada": fundo claro com ruído leve e linhas de texto."""
    image = Image.effect_noise(size, 12).convert("L").point(lambda v: 200 + v // 5)
    draw = ImageDraw.Draw(image)
    margin, step = size[0] // 14, max(8, size[1] // 50)
    for row, y in enumerate(range(margin, size[1] - margin, step)):
        draw.rectangle((margin, y, size[0] - margin - (row % 5) * margin, y + step // 3), fill=40)
    if color:
        image = Image.merge("RGB", (image, image.point(lambda v: v * 0.9), image.point(lambda v: v * 0.7)))
    return image


# Página pequena (4 x 5,5 polegadas) para os testes serem rápidos: a imagem de 1200 px de
# largura fica com 300 DPI, como um escaneado comum.
PAGE = (288, 396)


def _pdf_with_image(path, image: Image.Image, box=(0, 0, *PAGE)):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    c = rl_canvas.Canvas(str(path), pagesize=PAGE)
    left, bottom, right, top = box
    c.drawImage(ImageReader(buffer), left, bottom, right - left, top - bottom)
    c.setFont("Helvetica", 12)
    c.drawString(72, 72, "texto da pagina")
    c.showPage()
    c.save()
    return path


def _images(path):
    return [image for page in PdfReader(str(path)).pages for image in page.images]


def test_medium_level_shrinks_a_scanned_page(tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    output = tmp_path / "out.pdf"

    result = CompressPDF().run(str(source), str(output), level="medium")

    assert result.written and result.images_recompressed == 1
    assert os.path.getsize(output) < os.path.getsize(source) * 0.5
    reader = PdfReader(str(output))
    assert "texto da pagina" in reader.pages[0].extract_text()
    (image,) = _images(output)
    # 1200 px em 4 polegadas = 300 DPI; o alvo do nível médio é 150 DPI.
    assert 560 <= image.image.width <= 640


def test_strong_level_is_smaller_than_medium(tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    medium, strong = tmp_path / "medium.pdf", tmp_path / "strong.pdf"

    CompressPDF().run(str(source), str(medium), level="medium")
    CompressPDF().run(str(source), str(strong), level="strong")

    assert os.path.getsize(strong) < os.path.getsize(medium)


def test_color_image_without_color_is_stored_in_grayscale(tmp_path):
    gray_in_rgb = _scan_like_image().convert("RGB")
    source = _pdf_with_image(tmp_path / "scan.pdf", gray_in_rgb)
    output = tmp_path / "out.pdf"

    CompressPDF().run(str(source), str(output), level="medium")

    (image,) = _images(output)
    assert image.image.mode == "L"


def test_colored_image_stays_in_color_unless_asked(tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image(color=True))
    color_output, gray_output = tmp_path / "color.pdf", tmp_path / "gray.pdf"

    CompressPDF().run(str(source), str(color_output), level="medium")
    CompressPDF().run(str(source), str(gray_output), level="medium", grayscale=True)

    assert _images(color_output)[0].image.mode == "RGB"
    assert _images(gray_output)[0].image.mode == "L"


def test_small_image_is_not_downsampled_by_page_size(tmp_path):
    # 600 px desenhados numa área de 1 polegada = 600 DPI efetivos: reduz para ~150 DPI
    # (150 px), não para o que caberia na página inteira.
    source = _pdf_with_image(tmp_path / "logo.pdf", _scan_like_image((600, 600)), box=(72, 200, 144, 272))
    output = tmp_path / "out.pdf"

    CompressPDF().run(str(source), str(output), level="medium")

    (image,) = _images(output)
    assert 140 <= image.image.width <= 160


def test_transparency_mask_is_kept(tmp_path):
    rgba = _scan_like_image((800, 800), color=True).convert("RGBA")
    rgba.putalpha(Image.linear_gradient("L").resize(rgba.size))
    source = tmp_path / "alpha.pdf"
    c = rl_canvas.Canvas(str(source), pagesize=PAGE)
    c.drawImage(ImageReader(rgba), 0, 0, 200, 200, mask="auto")
    c.showPage()
    c.save()
    output = tmp_path / "out.pdf"

    CompressPDF().run(str(source), str(output), level="medium")

    reader = PdfReader(str(output))
    xobjects = reader.pages[0]["/Resources"]["/XObject"]
    images = [xobjects[name].get_object() for name in xobjects]
    assert any("/SMask" in image for image in images)


def test_light_level_does_not_touch_jpeg_images(tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    medium = tmp_path / "medium.pdf"
    CompressPDF().run(str(source), str(medium), level="medium")
    output = tmp_path / "light.pdf"

    result = CompressPDF().run(str(medium), str(output), level="light")

    assert result.images_recompressed == 0


def test_result_that_is_not_smaller_is_not_written(make_pdf, tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    once = tmp_path / "once.pdf"
    CompressPDF().run(str(source), str(once), level="strong")
    output = tmp_path / "twice.pdf"

    result = CompressPDF().run(str(once), str(output), level="strong")

    assert not result.written
    assert not output.exists()
    assert result.compressed_size >= result.original_size


def test_invalid_level_is_rejected(make_pdf, tmp_path):
    with pytest.raises(ValueError, match="Nível"):
        CompressPDF().run(str(make_pdf("doc.pdf", [(200, 200)])), str(tmp_path / "o.pdf"), level="max")


def test_cancel_before_writing_leaves_nothing(tmp_path):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    output = tmp_path / "out.pdf"
    progress = Progress()
    progress.cancel()

    with pytest.raises(OperationCancelled):
        CompressPDF().run(str(source), str(output), level="medium", progress=progress)
    assert not output.exists()


def test_ghostscript_result_is_used_only_when_smaller(tmp_path, monkeypatch):
    source = _pdf_with_image(tmp_path / "scan.pdf", _scan_like_image())
    calls = []

    def fake_run(command, progress, timeout, program=""):
        calls.append(command)
        target = next(arg.split("=", 1)[1] for arg in command if arg.startswith("-sOutputFile="))
        with open(target, "wb") as f:
            f.write(b"%PDF-1.7 menor")
        return 0, b""

    monkeypatch.setattr(compress, "find_ghostscript", lambda: "gswin64c")
    monkeypatch.setattr(compress, "run_cancellable", fake_run)
    output = tmp_path / "out.pdf"

    result = CompressPDF().run(str(source), str(output), level="strong", use_ghostscript=True)

    assert result.used_ghostscript
    assert output.read_bytes() == b"%PDF-1.7 menor"
    assert "-dPDFSETTINGS=/screen" in calls[0]


def test_ghostscript_missing_is_a_clear_error(make_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(compress, "find_ghostscript", lambda: None)

    with pytest.raises(RuntimeError, match="Ghostscript não encontrado"):
        CompressPDF().run(str(make_pdf("doc.pdf", [(200, 200)])), str(tmp_path / "o.pdf"), use_ghostscript=True)
