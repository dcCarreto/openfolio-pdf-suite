"""Extração de texto de arquivos PDF."""

from .base import PDFOperation, open_reader


class ExtractText(PDFOperation):
    """Extrai todo o texto de um PDF para um arquivo .txt."""

    def run(self, input_path: str, output_path: str) -> None:
        reader = open_reader(input_path)
        text = "\n\n".join(page.extract_text() for page in reader.pages)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
