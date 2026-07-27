"""Redação real (remoção definitiva de conteúdo) e sanitização de PDFs.

Redação: pypdf não tem nenhuma função de redação pronta, e remover só o texto de dentro de
um retângulo exigiria interpretar manualmente o content stream do PDF (matrizes de posição
de texto) — um projeto grande por si só, com risco real de deixar dado "por baixo"
recuperável, que é exatamente o tipo de falha que uma ferramenta de redação existe para
evitar. A abordagem aqui é a comprovadamente segura (confirmada nesta sessão): renderiza a
página inteira via pypdfium2, desenha os retângulos pretos por cima e substitui a página
inteira por essa imagem achatada — não sobra texto nem vetor original para recuperar.
Efeito colateral aceito: a página inteira perde a camada de texto pesquisável, não só a
área marcada.

Sanitizar: um PdfWriter novo (sem clone_from) já não carrega metadados, JavaScript nem
anexos do documento original (eles vivem em `/Info` e `/Names`, no catálogo, que só existem
no resultado se algo os adicionar de volta) — confirmado empiricamente nesta sessão com um
PDF de teste contendo os três. Isso cobre JavaScript em nível de documento, mas não
JavaScript embutido em ações de anotação (`/A` de um Link, ou `/AA` de um campo de
formulário), que sobrevive à cópia normal da página quando `remove_annotations=False` — por
isso essas ações são varridas anotação por anotação, à parte, para que a garantia "JavaScript
é sempre removido" valha de verdade. Metadados e anotações/comentários (sem JS) são opcionais
porque o usuário pode querer preservá-los.
"""

import io
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .base import PDFOperation

_REDACT_SCALE = 300 / 72  # mesma resolução usada em core/ocr.py


@dataclass
class RedactionRect:
    """Uma área marcada para redação, em pontos PDF (origem inferior-esquerda)."""

    page_index: int
    left: float
    bottom: float
    right: float
    top: float


class RedactDocument(PDFOperation):
    """Remove definitivamente o conteúdo das áreas marcadas, achatando a página em imagem."""

    def run(self, input_path: str, output_path: str, rects: list[RedactionRect]) -> int:
        rects_by_page: dict[int, list[RedactionRect]] = {}
        for rect in rects:
            rects_by_page.setdefault(rect.page_index, []).append(rect)

        reader = PdfReader(input_path)
        pdfium_doc = pdfium.PdfDocument(input_path)
        writer = PdfWriter()
        pages_redacted = 0

        for index, page in enumerate(reader.pages):
            page_rects = rects_by_page.get(index)
            if not page_rects:
                writer.add_page(page)
                continue

            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            image = pdfium_doc[index].render(scale=_REDACT_SCALE).to_pil()

            buffer = io.BytesIO()
            c = rl_canvas.Canvas(buffer, pagesize=(width, height))
            c.drawImage(ImageReader(image), 0, 0, width=width, height=height)
            c.setFillColorRGB(0, 0, 0)
            for rect in page_rects:
                c.rect(rect.left, rect.bottom, rect.right - rect.left, rect.top - rect.bottom, fill=1, stroke=0)
            c.showPage()
            c.save()
            buffer.seek(0)

            writer.add_page(PdfReader(buffer).pages[0])
            pages_redacted += 1

        with open(output_path, "wb") as f:
            writer.write(f)
        return pages_redacted


def _is_javascript_action(action) -> bool:
    return action is not None and action.get_object().get("/S") == "/JavaScript"


def _strip_annotation_javascript(annotation_ref) -> None:
    """Remove ações de JavaScript de uma anotação, preservando o restante (link, aparência etc.).

    `/A` dispara ao ativar a anotação (ex.: clicar num Link); `/AA` é o dicionário de "ações
    adicionais" por evento (ex.: campos de formulário disparando JS em keystroke/format/
    validate/calculate). Qualquer uma das duas pode carregar uma ação de Subtype /JavaScript.
    """
    annotation = annotation_ref.get_object()

    action = annotation.get("/A")
    if _is_javascript_action(action):
        del annotation["/A"]

    additional_actions = annotation.get("/AA")
    if additional_actions is not None:
        aa = additional_actions.get_object()
        for trigger in list(aa.keys()):
            if _is_javascript_action(aa[trigger]):
                del aa[trigger]


class SanitizeDocument(PDFOperation):
    """Remove metadados, JavaScript, anexos e (opcionalmente) anotações de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        remove_metadata: bool = True,
        remove_annotations: bool = False,
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()  # sem clone_from: já não carrega metadados, JS nem anexos

        for page in reader.pages:
            if remove_annotations and "/Annots" in page:
                del page["/Annots"]
            elif "/Annots" in page:
                for annotation_ref in page["/Annots"]:
                    _strip_annotation_javascript(annotation_ref)
            writer.add_page(page)

        if not remove_metadata and reader.metadata:
            writer.add_metadata(reader.metadata)

        with open(output_path, "wb") as f:
            writer.write(f)
