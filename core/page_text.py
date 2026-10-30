"""O texto de uma página do ponto de vista de quem lê: qual caractere está sob o mouse e onde
começam e terminam a palavra e a linha dele (duplo e triplo clique no visualizador)."""

import pypdfium2.raw as pdfium_c

# Do mais justo ao mais folgado: arrastar para a margem ou o fim da linha pega o caractere
# mais próximo, em vez de perder a seleção. O pdfium aplica metade de cada valor de cada lado do
# caractere; o último alcança qualquer ponto de uma página comum.
_TOLERANCES = (6, 20, 60, 200, 600, 3000)
_LINE_BREAKS = "\r\n"
_PERMISSION_EXTRACT = 1 << 4  # bit 5 de /P (ISO 32000-1, tabela 22)


def char_at(textpage, x: float, y: float, exact: bool = False) -> int | None:
    """O índice do caractere em (x, y), no espaço do usuário do PDF, ou o mais próximo (com
    `exact`, só um que esteja praticamente sob o ponto)."""
    for tolerance in _TOLERANCES[:1] if exact else _TOLERANCES:
        index = textpage.get_index(x, y, tolerance, tolerance)
        if index is not None and index >= 0:
            return index
    return None


def can_copy_text(document) -> bool:
    """Se o autor permite copiar o texto do `document` (do pypdfium2). Quem chama segura o
    PDFIUM_LOCK. Sem criptografia o pdfium devolve todas as permissões."""
    return bool(pdfium_c.FPDF_GetDocPermissions(document.raw) & _PERMISSION_EXTRACT)


def _char(textpage, index: int) -> str:
    return chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, index))


def _span(textpage, index: int, belongs) -> tuple[int, int]:
    """(início, quantidade) do trecho em volta de `index` cujos caracteres satisfazem `belongs`."""
    total = textpage.count_chars()
    first = last = index
    while first > 0 and belongs(_char(textpage, first - 1)):
        first -= 1
    while last < total - 1 and belongs(_char(textpage, last + 1)):
        last += 1
    return first, last - first + 1


def word_range(textpage, index: int) -> tuple[int, int]:
    """A palavra em `index` (com hífen e apóstrofo dentro dela); fora de uma palavra, só o caractere."""
    if not _is_word_char(_char(textpage, index)):
        return index, 1
    return _span(textpage, index, _is_word_char)


def line_range(textpage, index: int) -> tuple[int, int]:
    """A linha em `index`, sem a quebra de linha."""
    if _char(textpage, index) in _LINE_BREAKS:
        return index, 1
    return _span(textpage, index, lambda char: char not in _LINE_BREAKS)


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char in "-_'’"
