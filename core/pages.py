"""Manipulação de páginas: rotação, reordenação, remoção, inserção, substituição e a
montagem feita no editor de páginas (`ArrangePages`).

Os índices recebidos aqui contam a partir de 0; a interface mostra e recebe páginas
contadas a partir de 1 e converte na passagem. As mensagens de erro falam em páginas
contadas a partir de 1, como o usuário as vê.
"""

import io
from collections.abc import Iterable

from pypdf import PdfReader, PdfWriter

from .base import open_reader, require_valid_page_index, write_pdf
from .document import pages_writer
from .messages import Message, plural_message


def _page_list(pages: Iterable[int]) -> str:
    return ", ".join(str(page + 1) for page in sorted(pages))


class RotatePages:
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


class ReorderPages:
    """Reordena as páginas de um PDF. `order` precisa citar cada página exatamente uma vez:
    uma lista incompleta descartaria páginas sem aviso."""

    def run(self, input_path: str, output_path: str, order: list[int]) -> None:
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for index in order:
            require_valid_page_index(total_pages, index)
        duplicated = {index for index in order if order.count(index) > 1}
        if duplicated:
            raise ValueError(plural_message(
                    len(duplicated),
                    "Página repetida na nova ordem: {pages}.",
                    "Páginas repetidas na nova ordem: {pages}.",
                    pages=_page_list(duplicated),
                ))
        missing = set(range(total_pages)) - set(order)
        if missing:
            raise ValueError(
                Message(
                    "A nova ordem precisa incluir todas as {total} páginas; faltam: {pages}. "
                    "Para tirar páginas, use Remover.",
                    total=total_pages,
                    pages=_page_list(missing),
                )
            )

        write_pdf(pages_writer([(reader, order)]), output_path)


class RemovePages:
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


class InsertPages:
    """Insere todas as páginas de outro PDF numa posição do documento."""

    def run(self, input_path: str, output_path: str, insert_path: str, at_index: int) -> None:
        reader = open_reader(input_path)
        insert_reader = open_reader(insert_path)
        total_pages = len(reader.pages)
        if not 0 <= at_index <= total_pages:
            raise ValueError(
                plural_message(
                    total_pages,
                    "Posição de inserção inválida: o documento tem 1 página; dá para inserir antes ou depois dela.",
                    "Posição de inserção inválida: o documento tem {count} páginas; dá para inserir antes da "
                    "página 1 até depois da página {count}.",
                )
            )

        parts = [
            (reader, list(range(at_index))),
            (insert_reader, list(range(len(insert_reader.pages)))),
            (reader, list(range(at_index, total_pages))),
        ]
        write_pdf(pages_writer(parts, properties_from=reader), output_path)


class ReplacePages:
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
                plural_message(
                    total_pages,
                    "Intervalo inválido: a página final precisa vir depois da inicial ({start}) e o documento "
                    "tem 1 página.",
                    "Intervalo inválido: a página final precisa vir depois da inicial ({start}) e o documento "
                    "tem {count} páginas.",
                    start=start_index + 1,
                )
            )

        parts = [
            (reader, list(range(start_index))),
            (replacement_reader, list(range(len(replacement_reader.pages)))),
            (reader, list(range(end_index, total_pages))),
        ]
        write_pdf(pages_writer(parts, properties_from=reader), output_path)


_A4 = (595.0, 842.0)


class ArrangePages:
    """Monta o documento a partir da lista de páginas do editor de páginas, num passo só.

    Cada item de `layout` é (página de origem, giro): a página de origem conta a partir de
    0 e pode se repetir (duplicar) ou ser None (página em branco, do tamanho da página
    anterior na lista); o giro, em graus no sentido horário, soma-se ao que a página já tem.
    Páginas que não aparecem na lista saem do documento, como em Remover.
    """

    def run(self, input_path: str, output_path: str, layout: list[tuple[int | None, int]]) -> None:
        if not layout:
            raise ValueError("A remoção resultaria em um PDF sem nenhuma página.")
        reader = open_reader(input_path)
        total_pages = len(reader.pages)
        for index, angle in layout:
            if index is not None:
                require_valid_page_index(total_pages, index)
            if angle % 90 != 0:
                raise ValueError("O ângulo de rotação precisa ser múltiplo de 90 graus.")

        blanks = _blank_pages(reader, layout)
        parts: list[tuple[PdfReader, list[int]]] = []
        blank_count = 0
        for index, _angle in layout:
            if index is not None:
                source, page = reader, index
            else:
                assert blanks is not None  # há páginas em branco na lista
                source, page = blanks, blank_count
                blank_count += 1
            if parts and parts[-1][0] is source:
                parts[-1][1].append(page)
            else:
                parts.append((source, [page]))

        writer = pages_writer(parts, properties_from=reader)
        for new_page, (_index, angle) in zip(writer.pages, layout):
            if angle % 360:
                new_page.rotate(angle)
        write_pdf(writer, output_path)


def _blank_pages(reader: PdfReader, layout: list[tuple[int | None, int]]) -> PdfReader | None:
    """As páginas em branco da lista, num documento à parte, cada uma do tamanho (como se
    vê na tela) da página anterior na lista, ou da seguinte se ela for a primeira."""
    sizes = []
    real = [item for item in layout if item[0] is not None]
    previous = real[0] if real else None
    for item in layout:
        if item[0] is not None:
            previous = item
            continue
        if previous is None:
            sizes.append(_A4)
            continue
        index, angle = previous
        assert index is not None  # `previous` só guarda páginas reais
        page = reader.pages[index]
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        sizes.append((height, width) if (page.rotation + angle) % 180 else (width, height))
    if not sizes:
        return None
    writer = PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width, height)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return PdfReader(buffer)
