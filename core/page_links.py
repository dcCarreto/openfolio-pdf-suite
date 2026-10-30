"""Os links de uma página, para o visualizador segui-los com um clique: os anotados no PDF
(para um site ou para outra página do documento) e os endereços escritos no texto sem link
("www.exemplo.com", "contato@exemplo.com"), que o pdfium reconhece sozinho. Criar e remover
links (Editar) fica em core/links.py.

Só saem links para sites (http, https) e e-mail (mailto). Outros esquemas (file:,
javascript:...) e as ações que abrem programas ou outros arquivos ficam de fora: um PDF não
deve conseguir rodar nada na máquina com um clique.
"""

import ctypes
from dataclasses import dataclass

import pypdfium2.raw as pdfium_c

from core.geometry import Rect

_SCHEMES = ("http://", "https://", "mailto:")


@dataclass(frozen=True)
class PageLink:
    """Uma área clicável da página: leva a `url` ou à página `target_page` (contando de 0),
    com `target_top` no alto da tela quando o destino diz a altura."""

    rect: Rect  # (esquerda, baixo, direita, cima), no espaço do usuário do PDF
    url: str = ""
    target_page: int | None = None
    target_top: float | None = None

    def contains(self, x: float, y: float) -> bool:
        left, bottom, right, top = self.rect
        return left <= x <= right and bottom <= y <= top


def safe_url(url: str) -> str:
    """O endereço, se for de site ou e-mail ("www." sem esquema vira http://); senão, ""."""
    url = url.strip()
    if url.lower().startswith("www."):
        url = "http://" + url
    return url if url.lower().startswith(_SCHEMES) else ""


def page_links(document, page) -> list[PageLink]:
    """Os links da `page` (uma página aberta do `document`, ambos do pypdfium2), os anotados
    primeiro. Quem chama segura o PDFIUM_LOCK."""
    links = _annotated_links(document.raw, page.raw)
    textpage = page.get_textpage()
    try:
        for link in _text_links(textpage.raw):
            # O texto de um link anotado também tem cara de endereço: vale o anotado.
            left, bottom, right, top = link.rect
            center = ((left + right) / 2, (bottom + top) / 2)
            if not any(other.contains(*center) for other in links):
                links.append(link)
    finally:
        textpage.close()
    return links


def _rect(left: float, bottom: float, right: float, top: float) -> Rect:
    return (min(left, right), min(bottom, top), max(left, right), max(bottom, top))


def _annotated_links(document, page) -> list[PageLink]:
    links = []
    position = ctypes.c_int(0)
    link = pdfium_c.FPDF_LINK()
    while pdfium_c.FPDFLink_Enumerate(page, ctypes.byref(position), ctypes.byref(link)):
        box = pdfium_c.FS_RECTF()
        if not pdfium_c.FPDFLink_GetAnnotRect(link, ctypes.byref(box)):
            continue
        rect = _rect(box.left, box.bottom, box.right, box.top)
        destination = pdfium_c.FPDFLink_GetDest(document, link)
        action = pdfium_c.FPDFLink_GetAction(link)
        if not destination and action:
            kind = pdfium_c.FPDFAction_GetType(action)
            if kind == pdfium_c.PDFACTION_URI:
                url = safe_url(_uri_path(document, action))
                if url:
                    links.append(PageLink(rect, url=url))
                continue
            if kind == pdfium_c.PDFACTION_GOTO:
                destination = pdfium_c.FPDFAction_GetDest(document, action)
        if destination:
            target = pdfium_c.FPDFDest_GetDestPageIndex(document, destination)
            if target >= 0:
                links.append(PageLink(rect, target_page=target, target_top=_destination_top(destination)))
    return links


def _uri_path(document, action) -> str:
    size = pdfium_c.FPDFAction_GetURIPath(document, action, None, 0)
    if size <= 1:
        return ""
    buffer = ctypes.create_string_buffer(size)
    pdfium_c.FPDFAction_GetURIPath(document, action, buffer, size)
    # A especificação pede ASCII; UTF-8 cobre os PDFs que põem acentos mesmo assim.
    return buffer.value.decode("utf-8", errors="replace")


def _destination_top(destination) -> float | None:
    has_x, has_y, has_zoom = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    x, y, zoom = pdfium_c.FS_FLOAT(), pdfium_c.FS_FLOAT(), pdfium_c.FS_FLOAT()
    found = pdfium_c.FPDFDest_GetLocationInPage(
        destination,
        ctypes.byref(has_x),
        ctypes.byref(has_y),
        ctypes.byref(has_zoom),
        ctypes.byref(x),
        ctypes.byref(y),
        ctypes.byref(zoom),
    )
    return float(y.value) if found and has_y.value else None


def _text_links(textpage) -> list[PageLink]:
    links = []
    web_links = pdfium_c.FPDFLink_LoadWebLinks(textpage)
    try:
        for index in range(pdfium_c.FPDFLink_CountWebLinks(web_links)):
            url = safe_url(_web_link_url(web_links, index))
            if not url:
                continue
            # Um endereço que quebra a linha tem uma área por linha, todas com o mesmo destino.
            for part in range(pdfium_c.FPDFLink_CountRects(web_links, index)):
                left, top, right, bottom = (ctypes.c_double() for _ in range(4))
                if pdfium_c.FPDFLink_GetRect(
                    web_links, index, part, ctypes.byref(left), ctypes.byref(top), ctypes.byref(right), ctypes.byref(bottom)
                ):
                    links.append(PageLink(_rect(left.value, bottom.value, right.value, top.value), url=url))
    finally:
        pdfium_c.FPDFLink_CloseWebLinks(web_links)
    return links


def _web_link_url(web_links, index: int) -> str:
    size = pdfium_c.FPDFLink_GetURL(web_links, index, None, 0)  # em unidades UTF-16, com o \0
    if size <= 1:
        return ""
    buffer = (ctypes.c_ushort * size)()
    pdfium_c.FPDFLink_GetURL(web_links, index, buffer, size)
    return bytes(buffer).decode("utf-16-le").rstrip("\0")
