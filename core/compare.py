"""Comparação de duas versões de um PDF: diff de texto por página e diff visual."""

import difflib
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageStat

from .base import PDFOperation, open_reader

_DIFF_SCALE = 1.5
_DIFF_THRESHOLD = 30  # diferença de luminância (0-255) a partir da qual um pixel conta como "mudou"
_HIGHLIGHT_ALPHA = 0.6


@dataclass
class PageTextDiff:
    page_index: int
    changed: bool
    diff_lines: list[str] = field(default_factory=list)


class CompareText(PDFOperation):
    """Compara o texto de duas versões de um PDF, página a página, usando `difflib` (a
    mesma lógica de diff de texto da biblioteca padrão do Python, sem reinventar nada)."""

    def run(self, path_a: str, path_b: str) -> list[PageTextDiff]:
        reader_a = open_reader(path_a)
        reader_b = open_reader(path_b)
        total_pages = max(len(reader_a.pages), len(reader_b.pages))

        results = []
        for index in range(total_pages):
            text_a = reader_a.pages[index].extract_text() if index < len(reader_a.pages) else ""
            text_b = reader_b.pages[index].extract_text() if index < len(reader_b.pages) else ""
            diff_lines = list(
                difflib.unified_diff(
                    text_a.splitlines(),
                    text_b.splitlines(),
                    fromfile="A",
                    tofile="B",
                    lineterm="",
                )
            )
            results.append(
                PageTextDiff(page_index=index, changed=bool(diff_lines), diff_lines=diff_lines)
            )
        return results


@dataclass
class VisualDiffResult:
    page_index: int
    status: str  # "compared" | "only_in_a" | "only_in_b" | "size_mismatch"
    changed_fraction: float | None = None
    output_path: str | None = None


def _highlight_diff(image_a: Image.Image, image_b: Image.Image) -> tuple[Image.Image, float]:
    diff = ImageChops.difference(image_a, image_b).convert("L")
    mask = diff.point(lambda pixel: 255 if pixel > _DIFF_THRESHOLD else 0)
    changed_fraction = ImageStat.Stat(mask).mean[0] / 255.0

    red_layer = Image.new("RGB", image_b.size, (255, 0, 0))
    highlighted = Image.composite(red_layer, image_b, mask)
    highlighted = Image.blend(image_b, highlighted, _HIGHLIGHT_ALPHA)
    return highlighted, changed_fraction


class CompareVisual(PDFOperation):
    """Gera uma imagem por página destacando em vermelho as diferenças visuais entre duas
    versões de um PDF (renderizadas via `pypdfium2`, já usado em `core/convert.py` e
    `core/redaction.py`). Páginas que só existem numa das versões, ou com tamanhos
    diferentes entre as versões, não geram imagem de diff — só são sinalizadas no
    resultado, para não produzir uma comparação enganosa pixel a pixel entre páginas que
    não correspondem uma à outra."""

    def run(self, path_a: str, path_b: str, output_dir: str, scale: float = _DIFF_SCALE) -> list[VisualDiffResult]:
        open_reader(path_a)  # recusa PDF protegido por senha
        open_reader(path_b)
        doc_a = pdfium.PdfDocument(path_a)
        doc_b = pdfium.PdfDocument(path_b)
        total_pages = max(len(doc_a), len(doc_b))

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = []
        for index in range(total_pages):
            if index >= len(doc_a):
                results.append(VisualDiffResult(page_index=index, status="only_in_b"))
                continue
            if index >= len(doc_b):
                results.append(VisualDiffResult(page_index=index, status="only_in_a"))
                continue

            image_a = doc_a[index].render(scale=scale).to_pil().convert("RGB")
            image_b = doc_b[index].render(scale=scale).to_pil().convert("RGB")
            if image_a.size != image_b.size:
                results.append(VisualDiffResult(page_index=index, status="size_mismatch"))
                continue

            highlighted, changed_fraction = _highlight_diff(image_a, image_b)
            output_path = output_dir_path / f"diff_page{index + 1}.png"
            highlighted.save(output_path)
            results.append(
                VisualDiffResult(
                    page_index=index,
                    status="compared",
                    changed_fraction=changed_fraction,
                    output_path=str(output_path),
                )
            )

        return results
