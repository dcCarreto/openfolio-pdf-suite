"""OCR: reconhecimento de texto em páginas de PDF que são só imagem (escaneadas).

Usa o Tesseract (via pytesseract). Os instaladores do app trazem uma cópia própria dele,
com inglês, português e a detecção de orientação (ver `find_tesseract`), então o usuário
não instala nada; rodando do código-fonte, usa um Tesseract instalado no sistema.

A técnica de gravação é a mesma de core/watermark.py (overlay via reportlab + merge_page),
só que o "overlay" aqui é texto invisível (setTextRenderMode(3)) sobre cada palavra
reconhecida — a imagem escaneada original nunca é alterada, só ganha uma camada de texto
pesquisável por cima. Cada palavra é esticada na horizontal (operador `Tz`) para ocupar a
largura exata da palavra na imagem: sem isso, selecionar ou realçar o texto pegava um
pedaço diferente do que aparece na tela.

Quais páginas recebem OCR (`mode`):

- "auto": páginas sem texto, e também páginas escaneadas que têm só um pouco de texto (um
  carimbo ou número de protocolo aplicado depois da digitalização) — uma imagem cobrindo a
  maior parte da página. Páginas que já têm texto de verdade, inclusive uma camada de OCR
  anterior, ficam como estão.
- "force": todas as páginas. Numa página que já tem OCR, o texto fica duplicado.
- "redo": tira o texto invisível (o de um OCR anterior, deste ou de outro programa) e decide
  como no "auto": as páginas escaneadas são reconhecidas de novo, as de texto de verdade
  ficam como estão. Serve para refazer um OCR ruim, com outro idioma ou mais DPI.

`straighten=True` endireita a página no documento, como a aba Limpar escaneados: gira o
conteúdo de uma página torta (até 5°) antes de reconhecer e, com `detect_orientation`, põe de
pé a página digitalizada de lado ou de cabeça para baixo (pelo `/Rotate`).

Com o pacote de orientação do Tesseract ("osd") instalado, `detect_orientation=True` detecta
páginas digitalizadas de lado ou de cabeça para baixo e reconhece o texto na orientação
certa; o texto invisível acompanha a direção das linhas na imagem.
"""

import functools
import os
import shutil
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import ContentStream

from .base import open_pdfium, open_reader, render_scale, write_pdf
from .fonts import SANS, register_fonts, text_width
from .geometry import PageGeometry
from .overlay import materialize_inherited_attributes, visual_overlay
from .progress import PDFIUM_LOCK, Progress, ensure_progress
from .scan_cleanup import ink_mask, rotate_content, skew_angle

_TESSERACT_CANDIDATES = [
    "tesseract",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\msys64\ucrt64\bin\tesseract.exe",  # o que o build do Windows leva (release.yml)
]

DEFAULT_DPI = 300  # resolução padrão de qualidade para OCR
_OCR_SCALE = DEFAULT_DPI / 72
_DEFAULT_MIN_CONFIDENCE = 30
MODES = ("auto", "force", "redo")

# Modo "auto": uma página com texto ainda recebe OCR se tiver menos que isto de texto e uma
# imagem cobrindo pelo menos esta fração dela (escaneado com carimbo de texto).
_STAMP_TEXT_LIMIT = 200
_SCAN_COVERAGE = 0.5


def _bundled_tesseract() -> Path | None:
    """A cópia do Tesseract que os instaladores trazem: na pasta do app empacotado pelo
    PyInstaller, com os idiomas em `tessdata/` ao lado (ver packaging/pyinstaller)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is None:
        return None
    return Path(bundle) / ("tesseract.exe" if sys.platform == "win32" else "tesseract")


def find_tesseract() -> str | None:
    """O Tesseract que vem com o app; rodando do código-fonte, um instalado no sistema (no
    PATH ou num local comum de instalação)."""
    bundled = _bundled_tesseract()
    if bundled is not None and bundled.is_file():
        # Os idiomas que vieram junto, e não os de um Tesseract instalado na máquina.
        os.environ["TESSDATA_PREFIX"] = str(bundled.parent / "tessdata")
        return str(bundled)
    for candidate in _TESSERACT_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    return None


def get_available_languages() -> list[str]:
    """Lista os idiomas de reconhecimento instalados no Tesseract (exclui 'osd', que é
    dado de orientação de página, não um idioma de reconhecimento de texto). O resultado
    fica em cache: perguntar ao Tesseract leva um processo externo por chamada."""
    tesseract_path = find_tesseract()
    if not tesseract_path:
        return []
    return [lang for lang in _installed_languages(tesseract_path) if lang != "osd"]


def has_orientation_data() -> bool:
    """Se o pacote "osd" (detecção de orientação) está instalado no Tesseract."""
    tesseract_path = find_tesseract()
    return bool(tesseract_path) and "osd" in _installed_languages(tesseract_path)


@functools.lru_cache(maxsize=4)
def _installed_languages(tesseract_path: str) -> tuple[str, ...]:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    try:
        return tuple(pytesseract.get_languages(config=""))
    except Exception:
        return ()


def _run_tesseract(image, language: str) -> dict:
    """Isolado numa função própria para poder ser substituído nos testes (o Tesseract é um
    binário externo; testar a lógica de posicionamento não deveria depender dele estar
    instalado na máquina que roda os testes)."""
    return pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)


def _detect_rotation(image) -> int:
    """Quantos graus, no sentido horário, a imagem precisa girar para o texto ficar de pé
    (0, 90, 180 ou 270), segundo o Tesseract. 0 se não der para detectar."""
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return 0
    rotate = int(osd.get("rotate", 0)) % 360
    return rotate if rotate in (0, 90, 180, 270) else 0


class OCRDocument:
    """Adiciona uma camada de texto invisível e pesquisável sobre páginas escaneadas de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        language: str = "eng",
        skip_pages_with_text: bool = True,
        min_confidence: int = _DEFAULT_MIN_CONFIDENCE,
        mode: str | None = None,
        dpi: int = DEFAULT_DPI,
        detect_orientation: bool = False,
        progress: Progress | None = None,
        straighten: bool = False,
    ) -> int:
        progress = ensure_progress(progress)
        mode = mode or ("auto" if skip_pages_with_text else "force")
        if mode not in MODES:
            raise ValueError(f"Modo de OCR inválido: {mode}")
        if not 72 <= dpi <= 1200:
            raise ValueError("O DPI do OCR precisa estar entre 72 e 1200.")
        if not language or any(not part for part in language.split("+")):
            raise ValueError("Escolha pelo menos um idioma de reconhecimento.")
        tesseract_path = find_tesseract()
        if not tesseract_path:
            raise RuntimeError(
                "O reconhecimento de texto não está instalado. Instale-o para usar esta ferramenta."
            )
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)
        register_fonts()
        pages_ocred = 0
        scale = dpi / 72

        total_pages = len(reader.pages)
        with PDFIUM_LOCK:
            pdfium_doc = open_pdfium(input_path)
        try:
            for index, page in enumerate(reader.pages):
                progress.update(index, total_pages, "Reconhecendo o texto")
                target = writer.pages[index]
                if mode == "redo" and remove_invisible_text(target, writer):
                    page = target  # decide pelo texto que sobrou
                with PDFIUM_LOCK:
                    pdfium_page = pdfium_doc[index]
                    needs_ocr = mode == "force" or _needs_ocr(page, pdfium_page)
                    if needs_ocr:
                        geometry = PageGeometry.from_pdfium_page(pdfium_page)
                        image = pdfium_page.render(scale=render_scale(pdfium_page, scale), may_draw_forms=False).to_pil()
                    pdfium_page.close()
                if not needs_ocr:
                    continue

                rotation = _detect_rotation(image) if detect_orientation else 0
                upright = image.rotate(-rotation, expand=True) if rotation else image
                if straighten and (angle := _skew(upright, scale)):
                    # O conteúdo e a imagem giram juntos: as caixas do Tesseract já saem no
                    # lugar das palavras endireitadas.
                    rotate_content(target, geometry, angle)
                    upright = upright.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor="white")
                data = _run_tesseract(upright, language)

                overlay_page = self._build_overlay(data, geometry, image.size, min_confidence, rotation)
                if overlay_page is not None:
                    target.merge_page(overlay_page)
                    pages_ocred += 1
                if straighten and rotation:
                    target.rotate(rotation)  # só muda como a página aparece; o texto fica onde está
        finally:
            with PDFIUM_LOCK:
                pdfium_doc.close()

        progress.update(total_pages, total_pages, "Gravando")
        write_pdf(writer, output_path)
        return pages_ocred

    def _build_overlay(
        self,
        data: dict,
        geometry: PageGeometry,
        image_size: tuple[int, int],
        min_confidence: int,
        rotation: int = 0,
    ):
        """Monta a página com o texto invisível, ou None se nenhuma palavra passou no filtro
        de confiança.

        As caixas do Tesseract estão em pixels da imagem que ele recebeu: a página como
        aparece na tela, girada `rotation` graus no sentido horário quando a orientação foi
        corrigida. Elas são levadas de volta à imagem original e daí ao espaço visual, que
        `visual_overlay` leva ao espaço do usuário. O texto cai sobre a palavra e corre na
        direção em que ela aparece, mesmo em páginas com `/Rotate` ou CropBox deslocada.
        """
        image_width, image_height = image_size
        scale = image_width / geometry.width

        def to_original(x: float, y: float) -> tuple[float, float]:
            if rotation == 90:
                return y, image_height - x
            if rotation == 180:
                return image_width - x, image_height - y
            if rotation == 270:
                return image_width - y, x
            return x, y

        def draw(canvas, _width: float, height: float) -> bool:
            wrote_any = False
            for i in range(len(data["text"])):
                text = str(data["text"][i]).strip()
                if not text:
                    continue
                try:
                    confidence = float(data["conf"][i])
                except (TypeError, ValueError):
                    continue
                if confidence < min_confidence:
                    continue

                left, top = data["left"][i], data["top"][i]
                box_width, box_height = data["width"][i] / scale, data["height"][i] / scale
                # Início da linha de base (canto inferior esquerdo da palavra), no espaço visual.
                px, py = to_original(left, top + data["height"][i])
                x, y = px / scale, height - py / scale

                font_size = max(1.0, box_height * 0.9)
                natural_width = text_width(text, SANS, font_size)
                canvas.saveState()
                canvas.translate(x, y)
                if rotation:
                    canvas.rotate(rotation)
                text_obj = canvas.beginText(0, 0)
                text_obj.setTextRenderMode(3)  # invisível: não desenha nada, mas fica pesquisável
                text_obj.setFont(SANS, font_size)
                if natural_width > 0 and box_width > 0:
                    text_obj.setHorizScale(100 * box_width / natural_width)
                text_obj.textOut(text)
                canvas.drawText(text_obj)
                canvas.restoreState()
                wrote_any = True
            return wrote_any

        return visual_overlay(geometry, draw)


def _skew(image, scale: float) -> float:
    """A inclinação da página (graus, anti-horário), medida como na aba Limpar escaneados, a
    100 DPI."""
    factor = (100 / 72) / scale
    small = image.convert("L").resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))))
    return skew_angle(ink_mask(small))


_SHOW_TEXT = {b"Tj", b"TJ", b"'", b'"'}
# O que só vale dentro de BT/ET; o resto (fonte, espaçamentos, cor) pode ficar fora e fica,
# para o texto seguinte, que às vezes conta com o estado deixado pelo bloco removido.
_TEXT_OBJECT_ONLY = {b"BT", b"ET", b"Td", b"TD", b"Tm", b"T*", *_SHOW_TEXT}
_INVISIBLE = 3  # modo de renderização de texto "nem preenche nem contorna"


def remove_invisible_text(page, writer: PdfWriter) -> bool:
    """Tira da página os blocos de texto (BT/ET) em que todo o texto é invisível (`3 Tr`),
    como a camada de um OCR. Devolve se tirou algum.

    shortcut: só o content stream da página, não os Form XObjects; um OCR gravado dentro de
    um formulário fica. Nenhum dos geradores comuns (Tesseract, OCRmyPDF, este app) faz isso.
    """
    contents = page.get_contents()
    if contents is None:
        return False
    stream = ContentStream(contents, writer)
    kept: list = []
    block: list | None = None
    mode, saved = 0, []
    shown = visible = removed = False
    for operands, operator in stream.operations:
        if operator == b"Tr" and operands:
            mode = int(operands[0])
        elif operator == b"q":
            saved.append(mode)
        elif operator == b"Q" and saved:
            mode = saved.pop()
        if operator == b"BT":
            block, shown, visible = [], False, False
        if block is None:
            kept.append((operands, operator))
            continue
        block.append((operands, operator))
        if operator in _SHOW_TEXT:
            shown, visible = True, visible or mode != _INVISIBLE
        if operator == b"ET":
            if shown and not visible:
                kept += [(o, op) for o, op in block if op not in _TEXT_OBJECT_ONLY]
                removed = True
            else:
                kept += block
            block = None
    kept += block or []  # BT sem ET: fica como estava
    if removed:
        stream.operations = kept
        page.replace_contents(stream)
    return removed


def _needs_ocr(pypdf_page, pdfium_page) -> bool:
    """Modo "auto" (ver o docstring do módulo). Chamar com `PDFIUM_LOCK`."""
    text = "".join((pypdf_page.extract_text() or "").split())
    if not text:
        return True
    if len(text) >= _STAMP_TEXT_LIMIT:
        return False
    page_area = pdfium_page.get_width() * pdfium_page.get_height()
    if page_area <= 0:
        return False
    for image in pdfium_page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,)):
        left, bottom, right, top = image.get_bounds()
        if (right - left) * (top - bottom) >= _SCAN_COVERAGE * page_area:
            return True
    return False
