"""Conversão de PDF para outros formatos e vice-versa."""

from pathlib import Path

from PIL import Image

from .base import READ, PDFOperation, atomic_output, open_pdfium, open_reader


class ConvertToImages(PDFOperation):
    """Converte páginas de um PDF em imagens."""

    def run(self, input_path: str, output_dir: str, scale: float = 2.0) -> list[str]:
        open_reader(input_path, purpose=READ)  # recusa PDF que não abre, com mensagem clara
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        pdf = open_pdfium(input_path)
        try:
            for index, page in enumerate(pdf):
                image = page.render(scale=scale).to_pil()
                output_path = output_dir_path / f"{stem}_page{index + 1}.png"
                image.save(output_path)
                output_paths.append(str(output_path))
        finally:
            pdf.close()

        return output_paths


class ConvertFromImages(PDFOperation):
    """Converte um conjunto de imagens em um PDF."""

    def run(self, input_paths: list[str], output_path: str) -> None:
        if not input_paths:
            raise ValueError("Informe ao menos uma imagem para converter.")
        images = []
        for path in input_paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        first_image, remaining_images = images[0], images[1:]
        with atomic_output(output_path) as temp_path:
            first_image.save(temp_path, format="PDF", save_all=True, append_images=remaining_images)
