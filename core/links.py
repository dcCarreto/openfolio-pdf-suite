"""Anotações de link (hyperlink) em arquivos PDF: URL externa ou destino interno (página)."""

import re
from dataclasses import dataclass

from pypdf import PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ArrayObject, NameObject

from .base import READ, PDFOperation, open_reader, require_valid_page_index, write_pdf
from .messages import Message

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_EMAIL_RE = re.compile(r"^[^@\s/]+@[^@\s/]+\.[^@\s/]+$")


def normalize_url(url: str) -> str:
    """Completa o endereço digitado sem esquema: "exemplo.com" vira "https://exemplo.com" e
    "ana@exemplo.com" vira "mailto:ana@exemplo.com". Sem isso o leitor tratava o endereço
    como um caminho relativo ao arquivo, e o link não abria."""
    url = url.strip()
    if not url or _SCHEME_RE.match(url):
        return url
    if _EMAIL_RE.match(url):
        return "mailto:" + url
    return "https://" + url.lstrip("/")


class AddLink(PDFOperation):
    """Adiciona uma anotação de link numa área de uma página, apontando para uma URL
    externa ou para outra página do mesmo documento."""

    def run(
        self,
        input_path: str,
        output_path: str,
        page_number: int,
        left: float,
        bottom: float,
        right: float,
        top: float,
        url: str | None = None,
        target_page: int | None = None,
    ) -> None:
        if bool(url) == (target_page is not None):
            raise ValueError("Informe uma URL ou uma página de destino — exatamente uma das duas.")

        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        require_valid_page_index(len(reader.pages), page_number)
        if target_page is not None:
            require_valid_page_index(len(reader.pages), target_page, label="Página de destino")

        writer = PdfWriter(clone_from=reader)
        if url:
            annotation = Link(rect=(left, bottom, right, top), url=normalize_url(url))
        else:
            annotation = Link(rect=(left, bottom, right, top), target_page_index=target_page)
        writer.add_annotation(page_number=page_number, annotation=annotation)

        write_pdf(writer, output_path)


@dataclass
class LinkInfo:
    """Descrição resumida de uma anotação de link já existente num PDF."""

    page_index: int
    link_index: int
    rect: tuple[float, float, float, float]
    target: str


def _destination_page(reader, destination) -> int | None:
    """Índice (a partir de 0) da página de um destino: array [página /XYZ ...] ou nome."""
    destination = destination.get_object() if hasattr(destination, "get_object") else destination
    if isinstance(destination, (str, bytes)):
        named = reader.named_destinations.get(str(destination))
        if named is None:
            return None
        try:
            return reader.get_destination_page_number(named)
        except Exception:
            return None
    if isinstance(destination, dict) and "/D" in destination:
        return _destination_page(reader, destination["/D"])
    if isinstance(destination, list) and destination:
        page_ref = destination[0]
        for index, page in enumerate(reader.pages):
            if page.indirect_reference is not None and page_ref == page.indirect_reference:
                return index
        if isinstance(page_ref, int):
            return page_ref  # destino remoto usa o número da página
    return None


def _describe_link_target(reader, annotation) -> str:
    action = annotation.get("/A")
    if action is not None:
        action_obj = action.get_object()
        if action_obj.get("/S") == "/URI":
            return str(action_obj.get("/URI", ""))
        if action_obj.get("/S") == "/GoTo":
            page = _destination_page(reader, action_obj.get("/D"))
            if page is not None:
                return Message("página {page}", page=page + 1)
        return Message("ação: {action}", action=str(action_obj.get("/S", "?")).lstrip("/"))
    if "/Dest" in annotation:
        page = _destination_page(reader, annotation["/Dest"])
        if page is not None:
            return Message("página {page}", page=page + 1)
        return Message("destino interno")
    return Message("sem destino")


class ListLinks(PDFOperation):
    """Lista as anotações de link existentes num PDF, com o índice usado por `RemoveLink`
    para identificar qual delas remover."""

    def run(self, input_path: str) -> list[LinkInfo]:
        reader = open_reader(input_path, purpose=READ)
        result = []
        for page_index, page in enumerate(reader.pages):
            link_index = 0
            for annotation_ref in page.get("/Annots", []):
                annotation = annotation_ref.get_object()
                if annotation.get("/Subtype") != "/Link":
                    continue
                rect = tuple(float(v) for v in annotation["/Rect"])
                result.append(
                    LinkInfo(
                        page_index=page_index,
                        link_index=link_index,
                        rect=rect,
                        target=_describe_link_target(reader, annotation),
                    )
                )
                link_index += 1
        return result


class RemoveLink(PDFOperation):
    """Remove uma anotação de link de uma página pelo índice devolvido por `ListLinks`
    (o índice é relativo aos links daquela página, não a todos os links do documento)."""

    def run(self, input_path: str, output_path: str, page_number: int, link_index: int) -> None:
        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=reader)
        page = writer.pages[page_number]
        annots = page.get("/Annots")
        if not annots:
            raise ValueError("Esta página não tem nenhum link.")

        link_refs = [a for a in annots if a.get_object().get("/Subtype") == "/Link"]
        if not 0 <= link_index < len(link_refs):
            raise ValueError(
                Message(
                    "O link {number} não existe: a página tem {count} link(s).",
                    number=link_index + 1,
                    count=len(link_refs),
                )
            )
        target_ref = link_refs[link_index]
        remaining = ArrayObject(a for a in annots if a != target_ref)
        page[NameObject("/Annots")] = remaining

        write_pdf(writer, output_path)
