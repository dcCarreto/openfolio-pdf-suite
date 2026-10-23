"""Conversão de arquivos XML para PDF: imprime o conteúdo formatado como texto.

As linhas longas são quebradas e continuam com recuo, em vez de sair da página (antes,
acima de ~108 caracteres o texto passava da borda, e acima de 150 era cortado). A fonte
mono embutida (`core/fonts.py`) cobre caracteres fora do Latin-1, e o arquivo é passado ao
parser em bytes, para que o `encoding` declarado no próprio XML seja respeitado.
"""

import xml.dom.minidom

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .base import atomic_output
from .fonts import MONO, register_fonts, text_width

_MARGIN = 36
_CONTINUATION_INDENT = "    "


class ConvertXMLToPDF:
    """Converte um arquivo XML para PDF, imprimindo o conteúdo indentado como texto."""

    def run(self, input_path: str, output_path: str, font_size: int = 8, landscape_pages: bool = False) -> None:
        with open(input_path, "rb") as f:
            raw_bytes = f.read()

        try:
            pretty = xml.dom.minidom.parseString(raw_bytes).toprettyxml(indent="  ")
            lines = [line for line in pretty.splitlines() if line.strip()]
        except Exception:
            lines = _decode(raw_bytes).splitlines() or [""]

        register_fonts()
        page_size = landscape(A4) if landscape_pages else A4
        width, height = page_size
        line_height = font_size + 2
        char_width = text_width("M", MONO, font_size)
        max_chars = max(20, int((width - 2 * _MARGIN) / char_width))

        with atomic_output(output_path) as temp_path:
            c = canvas.Canvas(temp_path, pagesize=page_size)
            c.setFont(MONO, font_size)
            y = height - _MARGIN

            for line in lines:
                for piece in wrap_code_line(line.expandtabs(4), max_chars):
                    if y < _MARGIN:
                        c.showPage()
                        c.setFont(MONO, font_size)
                        y = height - _MARGIN
                    c.drawString(_MARGIN, y, piece)
                    y -= line_height

            c.save()


def _decode(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        # latin-1 mapeia todo byte 0-255, então nunca falha; é o fallback mais seguro para
        # XML legado que não declara (ou não segue) UTF-8.
        return raw_bytes.decode("latin-1")


def wrap_code_line(line: str, max_chars: int) -> list[str]:
    """Quebra uma linha de código em pedaços de até `max_chars` caracteres. As continuações
    ganham o recuo da linha original mais um recuo extra; a quebra prefere um espaço."""
    if len(line) <= max_chars:
        return [line]
    indent = line[: len(line) - len(line.lstrip(" "))]
    continuation = indent + _CONTINUATION_INDENT
    if len(continuation) > max_chars // 2:
        continuation = _CONTINUATION_INDENT  # recuo enorme: não sobraria espaço para o texto

    pieces: list[str] = []
    rest, prefix = line, ""
    while len(prefix) + len(rest) > max_chars:
        room = max_chars - len(prefix)
        cut = rest.rfind(" ", len(indent) + 1 if not pieces else 1, room + 1)
        if cut <= 0:
            cut = room
        pieces.append(prefix + rest[:cut].rstrip())
        rest = rest[cut:].lstrip(" ")
        prefix = continuation
    if rest:
        pieces.append(prefix + rest)
    return pieces
