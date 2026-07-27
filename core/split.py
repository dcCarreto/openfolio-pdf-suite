"""Divisão de um arquivo PDF em múltiplos documentos."""

from pathlib import Path

from pypdf import PdfWriter

from .base import PDFOperation, open_reader


class SplitPDF(PDFOperation):
    """Divide um PDF em partes conforme os critérios informados."""

    def run(
        self, input_path: str, output_dir: str, pages_per_file: int = 1
    ) -> list[str]:
        if pages_per_file < 1:
            raise ValueError("pages_per_file deve ser maior ou igual a 1.")
        reader = open_reader(input_path)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        total_pages = len(reader.pages)
        for start in range(0, total_pages, pages_per_file):
            end = min(start + pages_per_file, total_pages)
            writer = PdfWriter()
            for page_index in range(start, end):
                writer.add_page(reader.pages[page_index])

            part_number = start // pages_per_file + 1
            output_path = output_dir_path / f"{stem}_part{part_number}.pdf"
            with open(output_path, "wb") as f:
                writer.write(f)
            output_paths.append(str(output_path))

        return output_paths
