"""Manipulação de páginas: rotação, reordenação e remoção."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index


class RotatePages(PDFOperation):
    """Rotaciona páginas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        angle: int = 90,
        pages: list[int] | None = None,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter()
        target_pages = set(pages) if pages is not None else None
        for index, page in enumerate(reader.pages):
            if target_pages is None or index in target_pages:
                page.rotate(angle)
            writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)


class ReorderPages(PDFOperation):
    """Reordena páginas de um PDF."""

    def run(self, input_path: str, output_path: str, order: list[int]) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for index in order:
            require_valid_page_index(total_pages, index, label="Página em order")

        writer = PdfWriter()
        for index in order:
            writer.add_page(reader.pages[index])
        with open(output_path, "wb") as f:
            writer.write(f)


class RemovePages(PDFOperation):
    """Remove páginas de um PDF."""

    def run(self, input_path: str, output_path: str, pages: list[int]) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        pages_to_remove = set(pages)
        remaining = total_pages - len(pages_to_remove.intersection(range(total_pages)))
        if remaining < 1:
            raise ValueError("A remoção resultaria em um PDF sem nenhuma página.")

        writer = PdfWriter()
        for index, page in enumerate(reader.pages):
            if index not in pages_to_remove:
                writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)


class InsertPages(PDFOperation):
    """Insere todas as páginas de outro PDF numa posição do documento."""

    def run(self, input_path: str, output_path: str, insert_path: str, at_index: int) -> None:
        reader = open_reader(input_path)
        insert_reader = open_reader(insert_path)
        total_pages = len(reader.pages)
        if not 0 <= at_index <= total_pages:
            raise ValueError(
                f"Posição de inserção inválida: {at_index} (o documento tem {total_pages} "
                f"página(s), posições válidas vão de 0 a {total_pages})."
            )

        writer = PdfWriter()
        for index in range(at_index):
            writer.add_page(reader.pages[index])
        for page in insert_reader.pages:
            writer.add_page(page)
        for index in range(at_index, total_pages):
            writer.add_page(reader.pages[index])

        with open(output_path, "wb") as f:
            writer.write(f)


class ReplacePages(PDFOperation):
    """Substitui um intervalo de páginas do documento pelas páginas de outro PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        replacement_path: str,
        start_index: int,
        end_index: int,
    ) -> None:
        reader = open_reader(input_path)
        replacement_reader = open_reader(replacement_path)
        total_pages = len(reader.pages)
        require_valid_page_index(total_pages, start_index, label="Página inicial")
        if not start_index < end_index <= total_pages:
            raise ValueError(
                f"Intervalo inválido: end_index ({end_index}) deve ser maior que start_index "
                f"({start_index}) e no máximo {total_pages}."
            )

        writer = PdfWriter()
        for index in range(start_index):
            writer.add_page(reader.pages[index])
        for page in replacement_reader.pages:
            writer.add_page(page)
        for index in range(end_index, total_pages):
            writer.add_page(reader.pages[index])

        with open(output_path, "wb") as f:
            writer.write(f)
