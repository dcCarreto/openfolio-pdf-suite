"""Conversão de PDF para outros formatos e vice-versa."""

from pathlib import Path

from PIL import Image

from .base import READ, PDFOperation, atomic_output, open_pdfium, open_reader
from .progress import PDFIUM_LOCK, Progress, ensure_progress


class ConvertToImages(PDFOperation):
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


class ConvertFromImages(PDFOperation):
    """Converte um conjunto de imagens em um PDF."""

    def run(self, input_paths: list[str], output_path: str, progress: Progress | None = None) -> None:
        progress = ensure_progress(progress)
        if not input_paths:
            raise ValueError("Informe ao menos uma imagem para converter.")
        images = []
        for path in progress.steps(input_paths, message="Lendo as imagens"):
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        first_image, remaining_images = images[0], images[1:]
        with atomic_output(output_path) as temp_path:
            first_image.save(temp_path, format="PDF", save_all=True, append_images=remaining_images)
