"""Impressão do documento aberto (A01).

O pdfium renderiza cada página (com anotações e campos de formulário) e o Qt a envia à
impressora escolhida no diálogo do sistema. A página é ajustada à área imprimível sem
distorcer e girada quando a orientação dela não bate com a do papel, como fazem os leitores
de PDF. Roda na thread de trabalho (`ui/tasks.py`): o Qt permite pintar num `QPrinter` fora
da thread da interface.
"""

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter

from core.base import PRINT, open_pdfium, open_reader
from core.messages import Message
from core.progress import PDFIUM_LOCK, OperationCancelled, Progress, ensure_progress

# Acima disso a impressora não ganha nitidez visível e cada página A4 passaria de 35 MB.
_MAX_DPI = 300


def page_count_for_printing(path: str) -> int:
    """Número de páginas, ou `RestrictedPDFError` se o autor não permite imprimir."""
    return len(open_reader(path, purpose=PRINT).pages)


def pages_to_print(printer: QPrinter, page_count: int, current_page: int, selected_pages: list[int]) -> list[int]:
    """Índices (a partir de 0) das páginas escolhidas no diálogo de impressão."""
    mode = printer.printRange()
    if mode == QPrinter.PrintRange.CurrentPage:
        return [current_page]
    if mode == QPrinter.PrintRange.Selection:
        return sorted(page for page in selected_pages if 0 <= page < page_count)
    if mode == QPrinter.PrintRange.PageRange:
        ranges = printer.pageRanges()
        return [index for index in range(page_count) if ranges.contains(index + 1)]
    return list(range(page_count))


def print_pages(path: str, printer: QPrinter, pages: list[int], progress: Progress | None = None) -> int:
    """Imprime `pages` de `path` em `printer`. Devolve o número de páginas enviadas."""
    progress = ensure_progress(progress)
    open_reader(path, purpose=PRINT)  # confere a permissão de novo: o arquivo pode ter mudado
    if not pages:
        raise ValueError(Message("Nenhuma página escolhida para imprimir."))

    # Com driver que não faz cópias sozinho, o Qt deixa as cópias para o aplicativo.
    copies = 1 if printer.supportsMultipleCopies() else max(1, printer.copyCount())
    sequence = pages * copies if printer.collateCopies() else [page for page in pages for _ in range(copies)]

    painter = QPainter()
    if not painter.begin(printer):
        raise ValueError(Message("Não foi possível iniciar a impressão."))
    with PDFIUM_LOCK:
        document = open_pdfium(path)
        document.init_forms()
    try:
        area = QRectF(0, 0, printer.width(), printer.height())
        scale = min(printer.resolution(), _MAX_DPI) / 72
        for printed, index in enumerate(progress.steps(sequence, message="Imprimindo páginas")):
            if printed:
                printer.newPage()
            with PDFIUM_LOCK:
                page = document[index]
                width, height = page.get_size()  # já com a /Rotate da página
                rotation = 90 if (width > height) != (area.width() > area.height()) else 0
                image = page.render(scale=scale, draw_annots=True, may_draw_forms=True, rotation=rotation).to_pil()
                page.close()
            fit = min(area.width() / image.width, area.height() / image.height)
            target = QRectF(0, 0, image.width * fit, image.height * fit)
            target.moveCenter(area.center())
            painter.drawImage(target, QImage(ImageQt(image)))
    except OperationCancelled:
        printer.abort()
        raise
    finally:
        painter.end()
        with PDFIUM_LOCK:
            document.close()
    return len(sequence)
