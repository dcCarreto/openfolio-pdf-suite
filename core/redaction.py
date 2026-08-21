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
import re
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .base import PDFOperation, open_reader

_REDACT_SCALE = 300 / 72  # mesma resolução usada em core/ocr.py

# Padrões comuns de dado sensível para sugestão automática de redação. Todos priorizam
# não deixar passar ocorrência real (a redação em si é sempre revisável/removível da lista
# de pendentes antes de aplicar, então um falso positivo custa pouco; um falso negativo
# custaria o dado vazando).
_PATTERNS: dict[str, re.Pattern] = {
    "cpf": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b"),
    "cnpj": re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}

PATTERN_KINDS = tuple(_PATTERNS.keys())


@dataclass
class RedactionRect:
    """Uma área marcada para redação, em pontos PDF (origem inferior-esquerda)."""

    page_index: int
    left: float
    bottom: float
    right: float
    top: float


class FindSensitiveData(PDFOperation):
    """Busca padrões de dado sensível (CPF, CNPJ, e-mail, telefone, cartão de crédito, ou
    uma expressão regular à parte) no texto do PDF e devolve um `RedactionRect` por
    ocorrência — para revisão do usuário antes de virar redação de verdade.

    Usa `pypdfium2` (já uma dependência do projeto, mesma biblioteca usada para renderizar
    a página que a redação depois rasteriza) para mapear cada caractere encontrado de volta
    a uma caixa em coordenadas PDF, do mesmo jeito que `ui/viewer/search.py` já faz para a
    busca de texto simples do visualizador — só que aqui a ocorrência vem de regex, não de
    string literal, então não dá pra usar a busca nativa do pdfium (que não suporta regex).
    Uma ocorrência que atravessa quebra de linha vira uma única caixa cobrindo as duas
    linhas: isso apenas redige uma área um pouco maior do que o necessário, nunca menor, o
    que é o lado seguro do erro para uma ferramenta de redação.
    """

    def run(
        self,
        input_path: str,
        kinds: list[str] | None = None,
        custom_pattern: str | None = None,
    ) -> list[RedactionRect]:
        open_reader(input_path)  # recusa PDF protegido por senha, mesma checagem das outras operações

        patterns = [_PATTERNS[kind] for kind in (kinds or []) if kind in _PATTERNS]
        if custom_pattern:
            try:
                patterns.append(re.compile(custom_pattern))
            except re.error as exc:
                raise ValueError(f"Expressão regular inválida: {exc}") from exc
        if not patterns:
            return []

        rects: list[RedactionRect] = []
        pdfium_doc = pdfium.PdfDocument(input_path)
        try:
            for page_index in range(len(pdfium_doc)):
                page = pdfium_doc[page_index]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                    char_count = textpage.count_chars()
                    for pattern in patterns:
                        for match in pattern.finditer(text):
                            start, end = match.start(), min(match.end(), char_count)
                            if start >= end:
                                continue
                            boxes = [textpage.get_charbox(i) for i in range(start, end)]
                            left = min(box[0] for box in boxes)
                            bottom = min(box[1] for box in boxes)
                            right = max(box[2] for box in boxes)
                            top = max(box[3] for box in boxes)
                            rects.append(RedactionRect(page_index, left, bottom, right, top))
                finally:
                    textpage.close()
        finally:
            pdfium_doc.close()

        return rects


class RedactDocument(PDFOperation):
    """Remove definitivamente o conteúdo das áreas marcadas, achatando a página em imagem."""

    def run(self, input_path: str, output_path: str, rects: list[RedactionRect]) -> int:
        rects_by_page: dict[int, list[RedactionRect]] = {}
        for rect in rects:
            rects_by_page.setdefault(rect.page_index, []).append(rect)

        reader = open_reader(input_path)
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
        reader = open_reader(input_path)
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
