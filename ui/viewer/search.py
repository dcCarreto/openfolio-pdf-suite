"""Busca de texto em documentos PDF, com a posição de cada ocorrência."""

from dataclasses import dataclass


@dataclass
class SearchMatch:
    page_index: int
    left: float
    bottom: float
    right: float
    top: float


class DocumentSearch:
    """Busca um termo em todas as páginas de um pypdfium2.PdfDocument."""

    def __init__(self, pdfium_document):
        self._document = pdfium_document

    def find_all(self, query: str) -> list[SearchMatch]:
        query = query.strip()
        if not query:
            return []

        matches: list[SearchMatch] = []
        for page_index in range(len(self._document)):
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
                        boxes = [
                            textpage.get_charbox(char_index + offset)
                            for offset in range(char_count)
                        ]
                        left = min(box[0] for box in boxes)
                        bottom = min(box[1] for box in boxes)
                        right = max(box[2] for box in boxes)
                        top = max(box[3] for box in boxes)
                        matches.append(SearchMatch(page_index, left, bottom, right, top))
                finally:
                    searcher.close()
            finally:
                textpage.close()

        return matches
