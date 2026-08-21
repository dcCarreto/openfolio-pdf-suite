"""Anotações de link (hyperlink) em arquivos PDF: URL externa ou destino interno (página)."""

from dataclasses import dataclass

from pypdf import PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ArrayObject, NameObject

from .base import PDFOperation, open_reader, require_valid_page_index


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

        writer = PdfWriter(clone_from=input_path)
        if url:
            annotation = Link(rect=(left, bottom, right, top), url=url)
        else:
            annotation = Link(rect=(left, bottom, right, top), target_page_index=target_page)
        writer.add_annotation(page_number=page_number, annotation=annotation)

        with open(output_path, "wb") as f:
            writer.write(f)


@dataclass
class LinkInfo:
    """Descrição resumida de uma anotação de link já existente num PDF."""

    page_index: int
    link_index: int
    rect: tuple[float, float, float, float]
    target: str


def _describe_link_target(annotation) -> str:
    action = annotation.get("/A")
    if action is not None:
        action_obj = action.get_object()
        if action_obj.get("/S") == "/URI":
            return str(action_obj.get("/URI", ""))
        return "ação: " + str(action_obj.get("/S", "desconhecida"))
    if "/Dest" in annotation:
        return "destino interno"
    return "sem destino"


class ListLinks(PDFOperation):
    """Lista as anotações de link existentes num PDF, com o índice usado por `RemoveLink`
    para identificar qual delas remover."""

    def run(self, input_path: str) -> list[LinkInfo]:
        reader = open_reader(input_path)
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
                        target=_describe_link_target(annotation),
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

        writer = PdfWriter(clone_from=input_path)
        page = writer.pages[page_number]
        annots = page.get("/Annots")
        if not annots:
            raise ValueError("Esta página não tem nenhum link.")

        link_refs = [a for a in annots if a.get_object().get("/Subtype") == "/Link"]
        if not 0 <= link_index < len(link_refs):
            raise ValueError(
                f"Índice de link inválido: {link_index} (a página tem {len(link_refs)} "
                f"link(s), de 0 a {len(link_refs) - 1})."
            )
        target_ref = link_refs[link_index]
        remaining = ArrayObject(a for a in annots if a != target_ref)
        page[NameObject("/Annots")] = remaining

        with open(output_path, "wb") as f:
            writer.write(f)
