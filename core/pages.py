"""Manipulação de páginas: rotação, reordenação, remoção, inserção e substituição.

Os índices recebidos aqui contam a partir de 0; a interface mostra e recebe páginas
contadas a partir de 1 e converte na passagem. As mensagens de erro falam em páginas
contadas a partir de 1, como o usuário as vê.
"""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, require_valid_page_index, write_pdf
from .document import pages_writer


def _page_list(pages: list[int]) -> str:
    return ", ".join(str(page + 1) for page in sorted(pages))


class RotatePages(PDFOperation):
    """Rotaciona páginas de um PDF (no sentido horário, em múltiplos de 90 graus)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        angle: int = 90,
        pages: list[int] | None = None,
    ) -> None:
        if angle % 90 != 0:
            raise ValueError("O ângulo de rotação precisa ser múltiplo de 90 graus.")
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        if pages is not None:
            for index in pages:
                require_valid_page_index(total_pages, index)

        writer = PdfWriter(clone_from=reader)
        targets = set(pages) if pages is not None else set(range(total_pages))
        for index in sorted(targets):
            writer.pages[index].rotate(angle)
        write_pdf(writer, output_path)


class ReorderPages(PDFOperation):
    """Reordena as páginas de um PDF. `order` precisa citar cada página exatamente uma vez:
    uma lista incompleta descartaria páginas sem aviso."""

    def run(self, input_path: str, output_path: str, order: list[int]) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for index in order:
            require_valid_page_index(total_pages, index)
        duplicated = {index for index in order if order.count(index) > 1}
        if duplicated:
            raise ValueError(f"Página(s) repetida(s) na nova ordem: {_page_list(duplicated)}.")
        missing = set(range(total_pages)) - set(order)
        if missing:
            raise ValueError(
                f"A nova ordem precisa incluir todas as {total_pages} páginas; faltam: "
                f"{_page_list(missing)}. Para tirar páginas, use Remover."
            )

        write_pdf(pages_writer([(reader, order)]), output_path)


class RemovePages(PDFOperation):
    """Remove páginas de um PDF. Marcadores, links e campos de formulário que apontavam
    para as páginas removidas saem junto, e o conteúdo delas não fica no arquivo."""

    def run(self, input_path: str, output_path: str, pages: list[int]) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for index in pages:
            require_valid_page_index(total_pages, index)
        to_remove = set(pages)
        kept = [index for index in range(total_pages) if index not in to_remove]
        if not kept:
            raise ValueError("A remoção resultaria em um PDF sem nenhuma página.")

        write_pdf(pages_writer([(reader, kept)]), output_path)


class InsertPages(PDFOperation):
    """Insere todas as páginas de outro PDF numa posição do documento."""

    def run(self, input_path: str, output_path: str, insert_path: str, at_index: int) -> None:
        reader = open_reader(input_path)
        insert_reader = open_reader(insert_path)
        total_pages = len(reader.pages)
        if not 0 <= at_index <= total_pages:
            raise ValueError(
                f"Posição de inserção inválida: o documento tem {total_pages} página(s); dá "
                f"para inserir antes da página 1 até depois da página {total_pages}."
            )

        parts = [
            (reader, list(range(at_index))),
            (insert_reader, list(range(len(insert_reader.pages)))),
            (reader, list(range(at_index, total_pages))),
        ]
        write_pdf(pages_writer(parts, properties_from=reader), output_path)


class ReplacePages(PDFOperation):
    """Substitui um intervalo de páginas do documento pelas páginas de outro PDF.
    `start_index` é inclusivo e `end_index`, exclusivo."""

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
                f"Intervalo inválido: a página final precisa vir depois da inicial "
                f"({start_index + 1}) e o documento tem {total_pages} página(s)."
            )

        parts = [
            (reader, list(range(start_index))),
            (replacement_reader, list(range(len(replacement_reader.pages)))),
            (reader, list(range(end_index, total_pages))),
        ]
        write_pdf(pages_writer(parts, properties_from=reader), output_path)
