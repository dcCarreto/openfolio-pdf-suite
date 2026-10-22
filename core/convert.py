"""Conversão de PDF para outros formatos e vice-versa."""

import io
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .base import READ, atomic_output, open_pdfium, open_reader
from .progress import PDFIUM_LOCK, Progress, ensure_progress


class ConvertToImages:
    """Converte páginas de um PDF em imagens."""

    def run(
        self, input_path: str, output_dir: str, scale: float = 2.0, progress: Progress | None = None
    ) -> list[str]:
        progress = ensure_progress(progress)
        open_reader(input_path, purpose=READ)  # recusa PDF que não abre, com mensagem clara
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        with PDFIUM_LOCK:
            pdf = open_pdfium(input_path)
            total_pages = len(pdf)
        try:
            for index in progress.steps(range(total_pages), total_pages, "Convertendo páginas"):
                with PDFIUM_LOCK:
                    page = pdf[index]
                    image = page.render(scale=scale).to_pil()
                    page.close()
                output_path = output_dir_path / f"{stem}_page{index + 1}.png"
                image.save(output_path)
                output_paths.append(str(output_path))
        finally:
            with PDFIUM_LOCK:
                pdf.close()

        return output_paths


# Tamanhos de página para imagens → PDF, em pontos (retrato; a orientação acompanha a imagem).
IMAGE_PAGE_SIZES = {
    "A4": (595.28, 841.89),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}
FIT_TO_IMAGE = "fit"
_MM = 72 / 25.4
_EXIF_ORIENTATION = 0x0112


class ConvertFromImages:
    """Converte um conjunto de imagens em um PDF, uma imagem por página.

    - `page_size`: "A4", "Letter", "Legal" ou "fit" (página do tamanho da imagem a `dpi`
      pontos por polegada). Nos tamanhos fixos, a página fica em paisagem quando a imagem é
      mais larga que alta, e a imagem é centralizada sem distorcer. Antes a página tinha o
      tamanho em pixels a 72 DPI: uma foto de 4000x3000 virava uma página de 141x106 cm.
    - `margin_mm`: margem em volta da imagem.
    - A orientação gravada pela câmera (EXIF) é aplicada: fotos de celular saem de pé.
    - Transparência é composta sobre fundo branco (antes ficava preta).
    - Uma imagem por vez na memória. JPEGs que não precisam de ajuste entram como estão,
      sem recompressão.
    """

    def run(
        self,
        input_paths: list[str],
        output_path: str,
        page_size: str = "A4",
        margin_mm: float = 0,
        dpi: float = 300,
        progress: Progress | None = None,
    ) -> None:
        progress = ensure_progress(progress)
        if not input_paths:
            raise ValueError("Informe ao menos uma imagem para converter.")
        if page_size != FIT_TO_IMAGE and page_size not in IMAGE_PAGE_SIZES:
            raise ValueError(f"Tamanho de página inválido: {page_size}")
        if margin_mm < 0:
            raise ValueError("A margem não pode ser negativa.")
        if dpi <= 0:
            raise ValueError("O DPI precisa ser maior que zero.")
        margin = margin_mm * _MM

        with atomic_output(output_path) as temp_path:
            pdf = rl_canvas.Canvas(temp_path)
            for path in progress.steps(input_paths, message="Lendo as imagens"):
                source, (pixel_width, pixel_height) = _prepared_image(path)
                if page_size == FIT_TO_IMAGE:
                    image_width = pixel_width / dpi * 72
                    image_height = pixel_height / dpi * 72
                    page_width, page_height = image_width + 2 * margin, image_height + 2 * margin
                else:
                    page_width, page_height = IMAGE_PAGE_SIZES[page_size]
                    if pixel_width > pixel_height:
                        page_width, page_height = page_height, page_width
                    available_width = page_width - 2 * margin
                    available_height = page_height - 2 * margin
                    if available_width <= 0 or available_height <= 0:
                        raise ValueError("A margem é maior que a página.")
                    scale = min(available_width / pixel_width, available_height / pixel_height)
                    image_width, image_height = pixel_width * scale, pixel_height * scale
                pdf.setPageSize((page_width, page_height))
                pdf.drawImage(
                    source,
                    (page_width - image_width) / 2,
                    (page_height - image_height) / 2,
                    image_width,
                    image_height,
                )
                pdf.showPage()
            progress.check()
            pdf.save()


def _prepared_image(path: str):
    """A imagem pronta para o reportlab (o próprio arquivo, se for um JPEG que não precisa
    de ajuste) e o tamanho dela em pixels, já na orientação certa."""
    with Image.open(path) as opened:
        is_jpeg = opened.format == "JPEG"
        orientation = opened.getexif().get(_EXIF_ORIENTATION, 1)
        if is_jpeg and orientation == 1 and opened.mode in ("RGB", "L"):
            return path, opened.size
        image = ImageOps.exif_transpose(opened)
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, "white")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
            image = flattened
        elif image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        if is_jpeg:
            image.save(buffer, format="JPEG", quality=95)  # foto girada: sem virar um PNG enorme
        else:
            image.save(buffer, format="PNG")
        buffer.seek(0)
        return ImageReader(buffer), image.size
