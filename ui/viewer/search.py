"""Busca de texto em documentos PDF, com a posição de cada ocorrência."""

from collections.abc import Iterator
from dataclasses import dataclass

from core.progress import PDFIUM_LOCK


@dataclass
class SearchMatch:
    page_index: int
    left: float
    bottom: float
    right: float
    top: float


class DocumentSearch:
    """Busca um termo nas páginas de um pypdfium2.PdfDocument.

    `iter_pages` entrega o resultado página a página, para o visualizador buscar aos poucos
    sem travar a janela em documentos longos; `find_all` busca tudo de uma vez.
    """

    def __init__(self, pdfium_document):
        self._document = pdfium_document

    def page_count(self) -> int:
        with PDFIUM_LOCK:
            return len(self._document)

    def find_all(self, query: str) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        for page_matches in self.iter_pages(query):
            matches.extend(page_matches)
        return matches

    def iter_pages(self, query: str) -> Iterator[list[SearchMatch]]:
        """As ocorrências de cada página, em ordem (uma lista, possivelmente vazia, por página)."""
        query = query.strip()
        if not query:
            return
        for page_index in range(self.page_count()):
            with PDFIUM_LOCK:
                page_matches = self._find_on_page(page_index, query)
            yield page_matches  # fora do `with`: a trava não fica presa entre uma página e outra

    def _find_on_page(self, page_index: int, query: str) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        page = self._document[page_index]
        textpage = page.get_textpage()
        try:
            searcher = textpage.search(query, match_case=False)
            try:
                while True:
                    match = searcher.get_next()
                    if match is None:
                        break
                    char_index, char_count = match
                    boxes = [textpage.get_charbox(char_index + offset) for offset in range(char_count)]
                    left = min(box[0] for box in boxes)
                    bottom = min(box[1] for box in boxes)
                    right = max(box[2] for box in boxes)
                    top = max(box[3] for box in boxes)
                    matches.append(SearchMatch(page_index, left, bottom, right, top))
            finally:
                searcher.close()
        finally:
            textpage.close()
            page.close()
        return matches
