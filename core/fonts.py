"""Fontes TrueType embutidas em todo texto que o app desenha nos PDFs.

As fontes base14 do PDF (Helvetica, Courier...) não são embutidas e só cobrem o WinAnsi
(Latin-1, mais ou menos): "Ł", "ő", "€" em alguns leitores, grego, cirílico e símbolos
saíam como "?" ou sumiam — em marca d'água, numeração, carimbos, edição de texto, OCR, XML e
na conversão do Office. As fontes DejaVu (licença livre, ver `data/fonts/LICENSE-DejaVu.txt`)
cobrem latim estendido, grego, cirílico e muitos símbolos, e o reportlab embute só os glifos
usados (subconjunto), então o arquivo quase não cresce. CJK continua fora da cobertura.
"""

import threading
from pathlib import Path

from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS_DIR = Path(__file__).resolve().parent / "data" / "fonts"

SANS = "OpenFolioSans"
SANS_BOLD = "OpenFolioSans-Bold"
MONO = "OpenFolioMono"

_FILES = {
    SANS: "DejaVuSans.ttf",
    SANS_BOLD: "DejaVuSans-Bold.ttf",
    MONO: "DejaVuSansMono.ttf",
}

_lock = threading.Lock()
_registered = False


def register_fonts() -> None:
    """Registra as fontes no reportlab (uma vez por processo, de qualquer thread)."""
    global _registered
    if _registered:
        return
    with _lock:
        if _registered:
            return
        for name, filename in _FILES.items():
            pdfmetrics.registerFont(TTFont(name, str(FONTS_DIR / filename)))
        pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=SANS_BOLD, italic=SANS, boldItalic=SANS_BOLD)
        _registered = True


def font_file(name: str) -> Path:
    return FONTS_DIR / _FILES[name]


def text_width(text: str, font: str, size: float) -> float:
    register_fonts()
    return pdfmetrics.stringWidth(text, font, size)


def wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Quebra `text` em linhas que cabem em `max_width`, respeitando as quebras de linha que
    já existem no texto. Uma palavra mais larga que a linha é quebrada no meio."""
    register_fonts()
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            lines.append("")
            continue
        for line in simpleSplit(paragraph, font, size, max_width):
            lines.extend(_split_long_word(line, font, size, max_width))
    return lines


def _split_long_word(line: str, font: str, size: float, max_width: float) -> list[str]:
    if pdfmetrics.stringWidth(line, font, size) <= max_width or len(line) <= 1:
        return [line]
    pieces, current = [], ""
    for char in line:
        if current and pdfmetrics.stringWidth(current + char, font, size) > max_width:
            pieces.append(current)
            current = char
        else:
            current += char
    if current:
        pieces.append(current)
    return pieces
