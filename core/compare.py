"""Comparação de duas versões de um PDF: diff de texto por página e diff visual."""

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .base import EXTRACT, READ, PDFOperation, open_pdfium, open_reader
from .progress import PDFIUM_LOCK, Progress, ensure_progress

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

    def run(self, path_a: str, path_b: str, progress: Progress | None = None) -> list[PageTextDiff]:
        progress = ensure_progress(progress)
        reader_a = open_reader(path_a, purpose=EXTRACT)
        reader_b = open_reader(path_b, purpose=EXTRACT)
        total_pages = max(len(reader_a.pages), len(reader_b.pages))

        results = []
        for index in progress.steps(range(total_pages), total_pages, "Comparando páginas"):
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

    def run(
        self,
        path_a: str,
        path_b: str,
        output_dir: str,
        scale: float = _DIFF_SCALE,
        progress: Progress | None = None,
    ) -> list[VisualDiffResult]:
        open_reader(path_a, purpose=READ)  # recusa, com mensagem clara, PDF que não abre
        open_reader(path_b, purpose=READ)
        with PDFIUM_LOCK:
            doc_a = open_pdfium(path_a)
            doc_b = open_pdfium(path_b)
        try:
            return self._compare(doc_a, doc_b, output_dir, scale, ensure_progress(progress))
        finally:
            with PDFIUM_LOCK:
                doc_a.close()
                doc_b.close()

    def _compare(self, doc_a, doc_b, output_dir: str, scale: float, progress: Progress) -> list[VisualDiffResult]:
        with PDFIUM_LOCK:
            pages_a, pages_b = len(doc_a), len(doc_b)
        total_pages = max(pages_a, pages_b)

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = []
        for index in progress.steps(range(total_pages), total_pages, "Comparando páginas"):
            if index >= pages_a:
                results.append(VisualDiffResult(page_index=index, status="only_in_b"))
                continue
            if index >= pages_b:
                results.append(VisualDiffResult(page_index=index, status="only_in_a"))
                continue

            with PDFIUM_LOCK:
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
