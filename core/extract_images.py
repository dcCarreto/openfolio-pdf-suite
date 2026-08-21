"""Extração e substituição de imagens embutidas em arquivos PDF."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index


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


@dataclass
class EmbeddedImageInfo:
    """Descrição resumida de uma imagem embutida numa página, para escolher qual substituir."""

    page_index: int
    image_index: int
    name: str
    width: int
    height: int


class ListEmbeddedImages(PDFOperation):
    """Lista as imagens embutidas em cada página de um PDF, com o índice usado por
    `ReplaceEmbeddedImage` para identificar qual delas substituir."""

    def run(self, input_path: str) -> list[EmbeddedImageInfo]:
        reader = open_reader(input_path)
        result = []
        for page_index, page in enumerate(reader.pages):
            for image_index, image_file in enumerate(page.images):
                result.append(
                    EmbeddedImageInfo(
                        page_index=page_index,
                        image_index=image_index,
                        name=image_file.name,
                        width=image_file.image.width,
                        height=image_file.image.height,
                    )
                )
        return result


class ReplaceEmbeddedImage(PDFOperation):
    """Substitui uma imagem já embutida num PDF por outra, mantendo a posição e o tamanho
    originais na página — usa `pypdf`'s `ImageFile.replace()`, que já resolve reescrever o
    stream da imagem no lugar certo do documento sem precisar mexer no content stream da
    página na unha."""

    def run(
        self,
        input_path: str,
        output_path: str,
        page_number: int,
        image_index: int,
        new_image_path: str,
    ) -> None:
        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=input_path)
        images = writer.pages[page_number].images
        if not 0 <= image_index < len(images):
            raise ValueError(
                f"Índice de imagem inválido: {image_index} (a página tem {len(images)} "
                f"imagem(ns), de 0 a {len(images) - 1})."
            )

        with Image.open(new_image_path) as new_image:
            new_image.load()
            images[image_index].replace(new_image)

        with open(output_path, "wb") as f:
            writer.write(f)
