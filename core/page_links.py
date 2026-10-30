"""Os links de uma página, para o visualizador segui-los com um clique: os anotados no PDF
(para um site ou para outra página do documento) e os endereços escritos no texto sem link
("www.exemplo.com", "contato@exemplo.com"), que o pdfium reconhece sozinho. Criar e remover
links (Editar) fica em core/links.py.

Saem links para sites (http, https), e-mail (mailto), outros PDFs (ação /GoToR, que abrem no
próprio app) e os comandos de navegação do leitor (ação /Named: próxima página, voltar...).
Outros esquemas (file:, javascript:...) e as ações que abrem programas ou outros tipos de arquivo
ficam de fora: um PDF não deve conseguir rodar nada na máquina com um clique.
"""

import ctypes
from dataclasses import dataclass, replace
from pathlib import Path

import pypdfium2.raw as pdfium_c

from core.base import READ, open_reader
from core.geometry import Rect

_SCHEMES = ("http://", "https://", "mailto:")
NAMED_ACTIONS = ("NextPage", "PrevPage", "FirstPage", "LastPage", "GoBack", "GoForward")
_NOT_NOTES = (pdfium_c.FPDF_ANNOT_LINK, pdfium_c.FPDF_ANNOT_WIDGET, pdfium_c.FPDF_ANNOT_POPUP)


@dataclass(frozen=True)
class PageLink:
    """Uma área clicável da página: leva a `url`, à página `target_page` (contando de 0, com
    `target_top` no alto da tela quando o destino diz a altura), a outro PDF (`file`, como está
    no link) ou a um comando de navegação (`named`, um de NAMED_ACTIONS)."""

    rect: Rect  # (esquerda, baixo, direita, cima), no espaço do usuário do PDF
    url: str = ""
    target_page: int | None = None
    target_top: float | None = None
    file: str = ""
    named: str = ""
    # O destino dentro do outro PDF: o número da página ou um destino com nome.
    file_page: int | None = None
    file_top: float | None = None
    file_destination: str = ""

    def contains(self, x: float, y: float) -> bool:
        left, bottom, right, top = self.rect
        return left <= x <= right and bottom <= y <= top


@dataclass(frozen=True)
class PageNote:
    """Um comentário com texto na página: o leitor o mostra com o mouse em cima."""

    rect: Rect
    author: str
    content: str

    def contains(self, x: float, y: float) -> bool:
        left, bottom, right, top = self.rect
        return left <= x <= right and bottom <= y <= top


def page_notes(page) -> list[PageNote]:
    """Os comentários com texto da `page` (aberta, do pypdfium2): notas, realces, carimbos...
    Links e campos de formulário têm o próprio comportamento. Quem chama segura o PDFIUM_LOCK."""
    notes = []
    for index in range(pdfium_c.FPDFPage_GetAnnotCount(page.raw)):
        annotation = pdfium_c.FPDFPage_GetAnnot(page.raw, index)
        if not annotation:
            continue
        try:
            if pdfium_c.FPDFAnnot_GetSubtype(annotation) in _NOT_NOTES:
                continue
            box = pdfium_c.FS_RECTF()
            content = _annotation_text(annotation, b"Contents")
            if content.strip() and pdfium_c.FPDFAnnot_GetRect(annotation, ctypes.byref(box)):
                rect = _rect(box.left, box.bottom, box.right, box.top)
                notes.append(PageNote(rect, _annotation_text(annotation, b"T"), content))
        finally:
            pdfium_c.FPDFPage_CloseAnnot(annotation)
    return notes


def _annotation_text(annotation, key: bytes) -> str:
    size = pdfium_c.FPDFAnnot_GetStringValue(annotation, key, None, 0)  # em bytes, com o \0
    if size <= 2:
        return ""
    buffer = (pdfium_c.FPDF_WCHAR * (size // 2))()
    pdfium_c.FPDFAnnot_GetStringValue(annotation, key, buffer, size)
    return bytes(buffer).decode("utf-16-le", errors="replace").rstrip("\0")


def safe_url(url: str) -> str:
    """O endereço, se for de site ou e-mail ("www." sem esquema vira http://); senão, ""."""
    url = url.strip()
    if url.lower().startswith("www."):
        url = "http://" + url
    return url if url.lower().startswith(_SCHEMES) else ""


def safe_pdf_file(name: str) -> str:
    """O nome, se for de um PDF local; endereços de rede ficam de fora (abrir um caminho de
    rede já entrega as credenciais do Windows ao servidor). Tudo o que começa com barra sai junto:
    o pdfium reescreve "//servidor/a.pdf" como "\\servidor\\a.pdf"."""
    name = name.strip()
    if not name.lower().endswith(".pdf") or "://" in name or name.startswith(("\\", "/")):
        return ""
    return name


def linked_pdf_path(name: str, folder: str) -> str:
    """O caminho do PDF de um link, relativo à `folder` do documento; "" se ele não existir."""
    path = Path(folder) / name
    return str(path) if safe_pdf_file(name) and path.is_file() else ""


def page_links(document, page, path: str | None = None, page_index: int = 0) -> list[PageLink]:
    """Os links da `page` (uma página aberta do `document`, ambos do pypdfium2), os anotados
    primeiro. Quem chama segura o PDFIUM_LOCK. O pdfium não diz qual é uma ação /Named: com o
    `path` e o `page_index`, só as páginas que têm alguma ação desconhecida são lidas pelo pypdf."""
    links = _annotated_links(document.raw, page.raw)
    if path is not None and any(link.file for link in links):
        links = _with_file_destinations(links, path, page_index)
    if path is not None and _has_unknown_action(page.raw):
        links.extend(_named_links(path, page_index))
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
        kind = pdfium_c.FPDFAction_GetType(action) if action else pdfium_c.PDFACTION_UNSUPPORTED
        # Antes do destino: o pdfium dá um destino também para /GoToR, e ele é uma página do
        # outro arquivo, não deste.
        if kind == pdfium_c.PDFACTION_REMOTEGOTO:
            name = safe_pdf_file(_action_file(action))
            if name:
                links.append(PageLink(rect, file=name))
            continue
        if not destination and action:
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


def _action_file(action) -> str:
    size = pdfium_c.FPDFAction_GetFilePath(action, None, 0)
    if size <= 1:
        return ""
    buffer = ctypes.create_string_buffer(size)
    pdfium_c.FPDFAction_GetFilePath(action, buffer, size)
    return buffer.value.decode("utf-8", errors="replace")


def _has_unknown_action(page) -> bool:
    position = ctypes.c_int(0)
    link = pdfium_c.FPDF_LINK()
    while pdfium_c.FPDFLink_Enumerate(page, ctypes.byref(position), ctypes.byref(link)):
        action = pdfium_c.FPDFLink_GetAction(link)
        if action and pdfium_c.FPDFAction_GetType(action) == pdfium_c.PDFACTION_UNSUPPORTED:
            return True
    return False


def _link_actions(path: str, page_index: int, kind: str) -> list[tuple[Rect, dict]]:
    """(área, ação) dos links da página com a ação `kind`, lidos pelo pypdf."""
    found = []
    try:
        page = open_reader(path, purpose=READ).pages[page_index]
        for reference in page.get("/Annots") or []:
            annotation = reference.get_object()
            action = annotation.get("/A")
            action = action.get_object() if action is not None else None
            if annotation.get("/Subtype") == "/Link" and isinstance(action, dict) and action.get("/S") == kind:
                left, bottom, right, top = (float(value) for value in annotation["/Rect"])
                found.append((_rect(left, bottom, right, top), action))
    except Exception:
        return found  # o arquivo não está mais lá ou o link é malformado: o que deu para ler
    return found


def _named_links(path: str, page_index: int) -> list[PageLink]:
    names = ((rect, str(action.get("/N", "")).lstrip("/")) for rect, action in _link_actions(path, page_index, "/Named"))
    return [PageLink(rect, named=name) for rect, name in names if name in NAMED_ACTIONS]


def _with_file_destinations(links: list[PageLink], path: str, page_index: int) -> list[PageLink]:
    """O pdfium não sabe o destino dentro do outro arquivo (resolveria um nome neste aqui)."""
    actions = _link_actions(path, page_index, "/GoToR")
    result = []
    for link in links:
        action = next((a for rect, a in actions if _same_rect(rect, link.rect)), None) if link.file else None
        result.append(_with_file_destination(link, action.get("/D")) if action else link)
    return result


def _same_rect(a: Rect, b: Rect) -> bool:
    return all(abs(one - other) < 0.01 for one, other in zip(a, b))


def _with_file_destination(link: PageLink, destination) -> PageLink:
    destination = destination.get_object() if destination is not None else None
    if isinstance(destination, str):
        return replace(link, file_destination=str(destination))
    if not isinstance(destination, list) or not destination or not isinstance(destination[0], (int, float)):
        return link
    kind = str(destination[1]) if len(destination) > 1 else ""
    top_index = {"/XYZ": 3, "/FitH": 2, "/FitBH": 2}.get(kind)
    top = destination[top_index] if top_index is not None and top_index < len(destination) else None
    return replace(link, file_page=int(destination[0]), file_top=float(top) if isinstance(top, (int, float)) else None)


def file_destination(path: str, link: PageLink) -> tuple[int, float | None] | None:
    """Página e altura de destino do `link` dentro do PDF em `path`, já aberto pelo usuário (com
    a senha, se tiver); None se o link não diz ou o destino não existe lá."""
    if link.file_page is not None:
        return link.file_page, link.file_top
    if not link.file_destination:
        return None
    try:
        reader = open_reader(path, purpose=READ)
        named = reader.named_destinations
        # Um nome pode vir como texto ou como nome do PDF, com a barra.
        destination = named.get(link.file_destination.lstrip("/")) or named.get("/" + link.file_destination.lstrip("/"))
        if destination is None:
            return None
        page = reader.get_destination_page_number(destination)
        top = destination.top
        return None if page is None else (page, float(top) if isinstance(top, (int, float)) else None)
    except Exception:
        return None


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
