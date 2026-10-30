"""Numeração de páginas em arquivos PDF.

As posições ("rodapé ao centro", "canto superior direito"...) valem para a página como ela
aparece na tela, também em páginas com `/Rotate` (ver `core/overlay.py`).
"""

import re

from pypdf import PdfWriter

from .base import open_reader, write_pdf
from .fonts import MONO, SANS, SANS_BOLD, register_fonts
from .geometry import PageGeometry
from .messages import DOC_PAGES, Message, plural_message
from .overlay import materialize_inherited_attributes, visual_overlay


def _stamp_text(
    input_path: str, output_path: str, label_for_page, position_for_page, font_size: float, font: str = SANS
) -> None:
    """Escreve um texto por página: `label_for_page(índice, total, leitor)` diz o texto (None
    deixa a página sem nada) e `position_for_page(largura, altura)` devolve (x, y,
    alinhamento) no espaço visual."""
    reader = open_reader(input_path)
    writer = PdfWriter(clone_from=reader)
    materialize_inherited_attributes(writer)
    register_fonts()
    total_pages = len(reader.pages)

    for index, (source_page, page) in enumerate(zip(reader.pages, writer.pages)):
        text = label_for_page(index, total_pages, reader)
        if text is None:
            continue

        def draw(canvas, width: float, height: float, text=text) -> None:
            x, y, align = position_for_page(width, height)
            canvas.setFont(font, font_size)
            if align == "left":
                canvas.drawString(x, y, text)
            elif align == "right":
                canvas.drawRightString(x, y, text)
            else:
                canvas.drawCentredString(x, y, text)

        if (overlay := visual_overlay(PageGeometry.from_pypdf_page(source_page), draw)) is not None:
            page.merge_page(overlay)

    write_pdf(writer, output_path)


NUMBER_STYLES = ("arabic", "roman", "ROMAN")
FONTS = (SANS, SANS_BOLD, MONO)


def to_roman(number: int) -> str:
    """Algarismos romanos em maiúsculas (1 a 3999)."""
    if not 1 <= number <= 3999:
        raise ValueError("Algarismos romanos vão de 1 a 3999.")
    result = ""
    for value, letters in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):  # fmt: skip
        count, number = divmod(number, value)
        result += letters * count
    return result


class AddPageNumbers:
    """Adiciona números de página a um PDF.

    - `position`: as mesmas do cabeçalho/rodapé ("footer-center" por padrão).
    - `style`: "arabic" (1, 2, 3), "roman" (i, ii, iii) ou "ROMAN" (I, II, III).
    - `pages` (índices a partir de 0) e `skip_first` escolhem as páginas numeradas; a
      primeira delas recebe `start_at` e as seguintes contam só as numeradas: com a capa
      pulada, a página 2 do arquivo mostra o número 1.
    - `use_page_labels`: escreve o rótulo de cada página (`/PageLabels`, como "iii" ou
      "A-1", o que o visualizador mostra) em vez de contar; `start_at` e `style` não valem.
    - `font`: uma das fontes do app (`FONTS`).
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        start_at: int = 1,
        font_size: int = 10,
        margin: float = 24,
        *,
        position: str = "footer-center",
        style: str = "arabic",
        skip_first: int = 0,
        pages: list[int] | None = None,
        use_page_labels: bool = False,
        font: str = SANS,
    ) -> None:
        if position not in _HF_POSITIONS:
            raise ValueError(f"Posição inválida: {position}")
        if style not in NUMBER_STYLES:
            raise ValueError(f"Estilo de numeração inválido: {style}")
        if font not in FONTS:
            raise ValueError(f"Fonte inválida: {font}")
        if pages is not None and not pages:
            raise ValueError("Informe as páginas a numerar.")
        if style != "arabic" and start_at < 1:
            raise ValueError("Algarismos romanos vão de 1 a 3999.")
        numbered: dict[int, int] = {}  # índice da página -> posição entre as numeradas

        def label(index: int, total: int, reader) -> str | None:
            if not numbered:
                chosen = range(total) if pages is None else sorted(set(pages))
                if not all(0 <= page < total for page in chosen):
                    raise ValueError(plural_message(total, *DOC_PAGES))
                numbered.update((page, order) for order, page in enumerate(p for p in chosen if p >= skip_first))
                if not numbered:
                    raise ValueError("Nenhuma página sobrou para numerar.")
            if index not in numbered:
                return None
            if use_page_labels:
                return reader.page_labels[index]
            number = start_at + numbered[index]
            if style == "arabic":
                return str(number)
            roman = to_roman(number)
            return roman if style == "ROMAN" else roman.lower()

        place = _HF_POSITIONS[position]
        _stamp_text(
            input_path,
            output_path,
            label,
            lambda width, height: place(width, height, margin),
            font_size,
            font,
        )


_BATES_POSITIONS = {
    "bottom-right": lambda w, h, margin: (w - margin, margin, "right"),
    "bottom-left": lambda w, h, margin: (margin, margin, "left"),
    "top-right": lambda w, h, margin: (w - margin, h - margin, "right"),
    "top-left": lambda w, h, margin: (margin, h - margin, "left"),
}


class AddBatesNumbers:
    """Adiciona numeração Bates a um PDF: prefixo + sequência global com zeros à esquerda
    (ex.: "CASO-000001"), usada em processos jurídicos para referenciar páginas de forma
    única entre vários documentos — diferente da numeração de página comum, que reinicia
    por documento e não serve como identificador único entre arquivos.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        prefix: str = "",
        start_at: int = 1,
        digits: int = 6,
        font_size: int = 9,
        margin: float = 18,
        position: str = "bottom-right",
    ) -> None:
        if position not in _BATES_POSITIONS:
            raise ValueError(f"Posição inválida: {position}")
        if digits < 1:
            raise ValueError("digits deve ser pelo menos 1.")

        place = _BATES_POSITIONS[position]
        _stamp_text(
            input_path,
            output_path,
            lambda index, _total, _reader: f"{prefix}{start_at + index:0{digits}d}",
            lambda width, height: place(width, height, margin),
            font_size,
        )


_HF_POSITIONS = {
    "header-left": lambda w, h, margin: (margin, h - margin, "left"),
    "header-center": lambda w, h, margin: (w / 2, h - margin, "center"),
    "header-right": lambda w, h, margin: (w - margin, h - margin, "right"),
    "footer-left": lambda w, h, margin: (margin, margin, "left"),
    "footer-center": lambda w, h, margin: (w / 2, margin, "center"),
    "footer-right": lambda w, h, margin: (w - margin, margin, "right"),
}


_PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\{(\w*)\}")
_PLACEHOLDERS = ("page", "pages")


def _check_placeholders(text: str) -> None:
    unknown = sorted(
        {match[1] for match in _PLACEHOLDER_RE.finditer(text) if match[1] is not None and match[1] not in _PLACEHOLDERS}
    )
    if unknown:
        raise ValueError(
            Message(
                "Marcador desconhecido no texto: {names}. Use {{page}} (número da página) e "
                "{{pages}} (total de páginas).",
                names=", ".join("{" + name + "}" for name in unknown),
            )
        )


def _fill_placeholders(text: str, page: int, pages: int) -> str:
    values = {"page": str(page), "pages": str(pages)}

    def replace(match: re.Match) -> str:
        token = match[0]
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        return values[match[1]]

    return _PLACEHOLDER_RE.sub(replace, text)


class AddHeaderFooter:
    """Adiciona um texto livre de cabeçalho ou rodapé a todas as páginas de um PDF.

    Suporta os marcadores `{page}` (número da página) e `{pages}` (total de páginas) no
    texto — ex.: `"Página {page} de {pages}"`. Qualquer outra chave é texto comum ("{",
    "}" soltos ou "{{"/"}}", que viram uma chave só); um marcador desconhecido como
    `{pagina}` é recusado, porque quase sempre é erro de digitação.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        text: str,
        position: str = "footer-center",
        font_size: int = 10,
        margin: float = 24,
    ) -> None:
        if position not in _HF_POSITIONS:
            raise ValueError(f"Posição inválida: {position}")
        _check_placeholders(text)

        place = _HF_POSITIONS[position]
        _stamp_text(
            input_path,
            output_path,
            lambda index, total, _reader: _fill_placeholders(text, index + 1, total),
            lambda width, height: place(width, height, margin),
            font_size,
        )
