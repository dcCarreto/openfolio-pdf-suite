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
PDF de teste contendo os três. JavaScript e anexos são sempre removidos (não faz sentido
uma ferramenta de sanitização manter JavaScript escondido de propósito); metadados e
anotações/comentários são opcionais porque o usuário pode querer preservá-los.
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
            writer.add_page(page)

        if not remove_metadata and reader.metadata:
            writer.add_metadata(reader.metadata)

        with open(output_path, "wb") as f:
            writer.write(f)
