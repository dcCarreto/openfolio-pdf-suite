"""Conversão de PDF para outros formatos e vice-versa."""

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from .base import PDFOperation


class ConvertToImages(PDFOperation):
    """Converte páginas de um PDF em imagens."""

    def run(self, input_path: str, output_dir: str, scale: float = 2.0) -> list[str]:
        pdf = pdfium.PdfDocument(input_path)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for index, page in enumerate(pdf):
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            output_path = output_dir_path / f"{stem}_page{index + 1}.png"
            image.save(output_path)
            output_paths.append(str(output_path))

        return output_paths


class ConvertFromImages(PDFOperation):
    """Converte um conjunto de imagens em um PDF."""

    def run(self, input_paths: list[str], output_path: str) -> None:
        if not input_paths:
            raise ValueError("Informe ao menos uma imagem para converter.")
        images = [Image.open(path).convert("RGB") for path in input_paths]
        first_image, remaining_images = images[0], images[1:]
        first_image.save(output_path, save_all=True, append_images=remaining_images)
