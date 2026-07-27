"""Extração de imagens embutidas em arquivos PDF."""

from pathlib import Path

from .base import PDFOperation, open_reader


class ExtractImages(PDFOperation):
    """Extrai as imagens embutidas nas páginas de um PDF."""

    def run(self, input_path: str, output_dir: str) -> list[str]:
        reader = open_reader(input_path)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for page_index, page in enumerate(reader.pages):
            for image_index, image_file in enumerate(page.images):
                suffix = Path(image_file.name).suffix or ".png"
                output_path = (
                    output_dir_path / f"{stem}_p{page_index + 1}_{image_index + 1}{suffix}"
                )
                with open(output_path, "wb") as f:
                    f.write(image_file.data)
                output_paths.append(str(output_path))

        return output_paths
