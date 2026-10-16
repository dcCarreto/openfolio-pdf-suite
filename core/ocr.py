"""OCR: reconhecimento de texto em páginas de PDF que são só imagem (escaneadas).

Não existe fallback em Python puro para isto (ao contrário da conversão de Office): sem um
motor de OCR de verdade instalado no sistema não há como reconhecer texto. Usa o Tesseract
(via pytesseract) do mesmo jeito que core/office_convert.py usa o LibreOffice quando
disponível — detectado por caminho, sem instalá-lo.

A técnica de gravação é a mesma de core/watermark.py (overlay via reportlab + merge_page),
só que o "overlay" aqui é texto invisível (reportlab suporta isso nativamente via
setTextRenderMode(3)) posicionado exatamente sobre cada palavra reconhecida — a imagem
escaneada original nunca é alterada, só ganha uma camada de texto pesquisável por cima.
"""

import shutil
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from pypdf import PdfWriter

from .base import PDFOperation, open_reader, write_pdf
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay
from .progress import PDFIUM_LOCK, Progress, ensure_progress

_TESSERACT_CANDIDATES = [
    "tesseract",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

_OCR_SCALE = 300 / 72  # ~300 DPI: resolução padrão de qualidade para OCR
_DEFAULT_MIN_CONFIDENCE = 30


def find_tesseract() -> str | None:
    """Procura o executável do Tesseract no PATH e em locais comuns de instalação."""
    for candidate in _TESSERACT_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if Path(candidate).is_file():
            return candidate
    return None


def get_available_languages() -> list[str]:
    """Lista os idiomas de reconhecimento instalados no Tesseract (exclui 'osd', que é
    dado de orientação de página, não um idioma de reconhecimento de texto)."""
    tesseract_path = find_tesseract()
    if not tesseract_path:
        return []
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    try:
        languages = pytesseract.get_languages(config="")
    except Exception:
        return []
    return [lang for lang in languages if lang != "osd"]


def _run_tesseract(image, language: str) -> dict:
    """Isolado numa função própria para poder ser substituído nos testes (o Tesseract é um
    binário externo; testar a lógica de posicionamento não deveria depender dele estar
    instalado na máquina que roda os testes)."""
    return pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)


class OCRDocument(PDFOperation):
    """Adiciona uma camada de texto invisível e pesquisável sobre páginas escaneadas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        language: str = "eng",
        skip_pages_with_text: bool = True,
        min_confidence: int = _DEFAULT_MIN_CONFIDENCE,
        progress: Progress | None = None,
    ) -> int:
        progress = ensure_progress(progress)
        tesseract_path = find_tesseract()
        if not tesseract_path:
            raise RuntimeError(
                "Tesseract OCR não encontrado. Instale o Tesseract para usar esta ferramenta."
            )
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)
        pages_ocred = 0

        total_pages = len(reader.pages)
        with PDFIUM_LOCK:
            pdfium_doc = pdfium.PdfDocument(input_path)
        try:
            for index, page in enumerate(reader.pages):
                progress.update(index, total_pages, "Reconhecendo o texto")
                if skip_pages_with_text and (page.extract_text() or "").strip():
                    continue

                with PDFIUM_LOCK:
                    pdfium_page = pdfium_doc[index]
                    geometry = PageGeometry.from_pdfium_page(pdfium_page)
                    image = pdfium_page.render(scale=_OCR_SCALE).to_pil()
                    pdfium_page.close()
                data = _run_tesseract(image, language)

                overlay_page = self._build_overlay(data, geometry, image.size, min_confidence)
                if overlay_page is not None:
                    writer.pages[index].merge_page(overlay_page)
                    pages_ocred += 1
        finally:
            with PDFIUM_LOCK:
                pdfium_doc.close()

        progress.update(total_pages, total_pages, "Gravando")
        write_pdf(writer, output_path)
        return pages_ocred

    def _build_overlay(
        self, data: dict, geometry: PageGeometry, image_size: tuple[int, int], min_confidence: int
    ):
        """Monta a página com o texto invisível, ou None se nenhuma palavra passou no filtro
        de confiança.

        As caixas do Tesseract estão em pixels da imagem renderizada, ou seja, no espaço
        visual (a página como aparece na tela); `visual_overlay` leva esse espaço ao do
        usuário. O texto cai sobre a palavra e corre na direção em que ela aparece, mesmo em
        páginas com `/Rotate` ou CropBox deslocada.
        """
        image_width, image_height = image_size
        scale_x = image_width / geometry.width
        scale_y = image_height / geometry.height

        def draw(canvas, _width: float, height: float) -> bool:
            wrote_any = False
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if not text:
                    continue
                try:
                    confidence = float(data["conf"][i])
                except (TypeError, ValueError):
                    continue
                if confidence < min_confidence:
                    continue

                x = data["left"][i] / scale_x
                box_height = data["height"][i] / scale_y
                y_top = height - data["top"][i] / scale_y
                y = y_top - box_height  # baseline aproximada, na base da caixa reconhecida

                text_obj = canvas.beginText(x, y)
                text_obj.setTextRenderMode(3)  # invisível: não desenha nada, mas fica pesquisável
                text_obj.setFont("Helvetica", max(1.0, box_height * 0.9))
                text_obj.textOut(text)
                canvas.drawText(text_obj)
                wrote_any = True
            return wrote_any

        return visual_overlay(geometry, draw)
