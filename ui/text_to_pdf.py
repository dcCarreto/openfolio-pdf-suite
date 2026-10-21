"""Conversão de HTML, Markdown e texto puro para PDF (A09), pelo `QTextDocument` do Qt.

O Qt já lê HTML (o subconjunto de rich text dele: títulos, parágrafos, listas, tabelas,
negrito/itálico, imagens locais) e Markdown (CommonMark com tabelas), quebra as linhas e as
páginas e grava em PDF com texto de verdade, pesquisável. Nada é buscado na internet nem
executado: imagens remotas e scripts do HTML ficam de fora. Fica aqui, e não em `core/`,
porque depende do Qt; como a impressão, roda na thread de trabalho.
"""

import functools
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QPageSize, QPdfWriter, QTextCursor, QTextDocument

from core.base import atomic_output
from core.fonts import MONO, SANS_BOLD, font_file
from core.xml_convert import _decode
from ui.pages.fill_sign_page import _sans_family

HTML_SUFFIXES = (".html", ".htm")
MARKDOWN_SUFFIXES = (".md", ".markdown")
SUFFIXES = HTML_SUFFIXES + MARKDOWN_SUFFIXES + (".txt",)
_MARGIN_MM = 20
# Elementos HTML sem fechamento. No Markdown, o Qt espera o fechamento de um `<img ...>` ou
# `<br>` escrito sem a barra e some com todo o texto seguinte (o README do projeto saía
# quase vazio); escritos `<img ... />` e `<br />`, saem certos.
_VOID_TAG = re.compile(r"<(area|br|col|embed|hr|img|input|source|wbr)\b([^<>]*?)\s*/?>", re.IGNORECASE)


@functools.cache
def _default_family() -> str:
    """A fonte embutida do app (com negrito e mono), para o PDF sair igual em qualquer
    máquina e cobrir os mesmos caracteres que as outras ferramentas."""
    for name in (SANS_BOLD, MONO):
        QFontDatabase.addApplicationFont(str(font_file(name)))
    return _sans_family()


def _absolute_image_paths(document: QTextDocument) -> None:
    """Troca o caminho relativo de cada imagem pelo absoluto e tira as imagens da internet.

    Para paginar, o `print_` do Qt trabalha numa cópia do documento, que perde a pasta-base:
    imagem relativa (a mais comum) saía como o ícone de imagem quebrada. Imagem da internet
    não é baixada (nada sai da máquina), então sairia sempre assim.
    """
    images = []
    block = document.begin()
    while block.isValid():
        for item in block:  # type: ignore[attr-defined]  # o stub não sabe iterar um QTextBlock
            fragment = item.fragment()
            if fragment.charFormat().isImageFormat():
                images.append((fragment.position(), fragment.length(), fragment.charFormat().toImageFormat()))
        block = block.next()
    cursor = QTextCursor(document)
    for position, length, image in reversed(images):  # de trás para frente: remover não desloca as anteriores
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        url = document.baseUrl().resolved(QUrl(image.name()))
        if url.scheme() in ("http", "https", "ftp"):
            cursor.removeSelectedText()
        else:
            image.setName(url.toString())
            cursor.setCharFormat(image)


def convert_text_to_pdf(input_path: str, output_path: str) -> None:
    suffix = Path(input_path).suffix.lower()
    text = _decode(Path(input_path).read_bytes())
    document = QTextDocument()
    document.setDefaultFont(QFont(_default_family(), 11))
    if suffix in HTML_SUFFIXES:
        document.setBaseUrl(QUrl.fromLocalFile(str(Path(input_path).resolve())))  # imagens relativas
        document.setHtml(text)
    elif suffix in MARKDOWN_SUFFIXES:
        document.setBaseUrl(QUrl.fromLocalFile(str(Path(input_path).resolve())))
        document.setMarkdown(_VOID_TAG.sub(r"<\1\2 />", text))
    else:
        document.setPlainText(text)
    _absolute_image_paths(document)

    with atomic_output(output_path) as temp_path:
        writer = QPdfWriter(temp_path)
        writer.setTitle(document.metaInformation(QTextDocument.MetaInformation.DocumentTitle) or Path(input_path).stem)
        writer.setPageLayout(
            QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Portrait,
                QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
                QPageLayout.Unit.Millimeter,
            )
        )
        document.print_(writer)
        del writer  # o arquivo só é fechado quando o QPdfWriter é destruído
