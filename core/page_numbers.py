"""Numeração de páginas em arquivos PDF.

As posições ("rodapé ao centro", "canto superior direito"...) valem para a página como ela
aparece na tela, também em páginas com `/Rotate` (ver `core/overlay.py`).
"""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader, write_pdf
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay


def _stamp_text(input_path: str, output_path: str, label_for_page, position_for_page, font_size: float) -> None:
    """Escreve um texto por página: `label_for_page(índice, total)` diz o texto e
    `position_for_page(largura, altura)` devolve (x, y, alinhamento) no espaço visual."""
    reader = open_reader(input_path)
    writer = PdfWriter(clone_from=reader)
    materialize_inherited_attributes(writer)
    total_pages = len(reader.pages)

    for index, (source_page, page) in enumerate(zip(reader.pages, writer.pages)):
        text = label_for_page(index, total_pages)

        def draw(canvas, width: float, height: float, text=text) -> None:
            x, y, align = position_for_page(width, height)
            canvas.setFont("Helvetica", font_size)
            if align == "left":
                canvas.drawString(x, y, text)
            elif align == "right":
                canvas.drawRightString(x, y, text)
            else:
                canvas.drawCentredString(x, y, text)

        page.merge_page(visual_overlay(PageGeometry.from_pypdf_page(source_page), draw))

    write_pdf(writer, output_path)


class AddPageNumbers(PDFOperation):
    """Adiciona números de página no rodapé de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        start_at: int = 1,
        font_size: int = 10,
        margin: float = 24,
    ) -> None:
        _stamp_text(
            input_path,
            output_path,
            lambda index, _total: str(start_at + index),
            lambda width, _height: (width / 2, margin, "center"),
            font_size,
        )


_BATES_POSITIONS = {
    "bottom-right": lambda w, h, margin: (w - margin, margin, "right"),
    "bottom-left": lambda w, h, margin: (margin, margin, "left"),
    "top-right": lambda w, h, margin: (w - margin, h - margin, "right"),
    "top-left": lambda w, h, margin: (margin, h - margin, "left"),
}


class AddBatesNumbers(PDFOperation):
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
            lambda index, _total: f"{prefix}{start_at + index:0{digits}d}",
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


class AddHeaderFooter(PDFOperation):
    """Adiciona um texto livre de cabeçalho ou rodapé a todas as páginas de um PDF.

    Suporta os placeholders `{page}` (número da página) e `{pages}` (total de páginas) no
    texto — ex.: `"Página {page} de {pages}"` — resolvidos por página com `str.format()`.
    Para escrever uma chave literal, use `{{` e `}}`.
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
        try:
            text.format(page=1, pages=1)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(
                f"Texto inválido ({exc}). Use {{page}} e {{pages}} como marcadores; para uma "
                "chave literal, escreva {{ ou }}."
            ) from exc

        place = _HF_POSITIONS[position]
        _stamp_text(
            input_path,
            output_path,
            lambda index, total: text.format(page=index + 1, pages=total),
            lambda width, height: place(width, height, margin),
            font_size,
        )
