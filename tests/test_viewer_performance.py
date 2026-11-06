"""Desempenho do visualizador: páginas pesadas renderizadas fora da thread da interface, o
cache das páginas prontas, miniaturas só à vista, tamanho das páginas sem abri-las e a
leitura da estrutura do PDF (avisos, campos, sumário, anexos) numa thread, de uma vez só."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

from core import base
from core.base import open_reader, shared_reader
from core.geometry import PageGeometry
from core.progress import PDFIUM_LOCK
from ui.annotation_state import AnnotationState
from ui.document_session import DocumentSession
from ui.redaction_state import RedactionState
from ui.viewer.document_details import read_details
from ui.viewer.page_renderer import PageRenderer, PixmapCache
from ui.viewer.pdf_viewer import CONTINUOUS, PdfViewer
from ui.viewer.render import logical_size


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait(condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.002)
    return condition()


def _rendering_done(viewer: PdfViewer) -> bool:
    QApplication.processEvents()
    return viewer._renderer.is_idle()


@pytest.fixture
def long_pdf(tmp_path):
    path = tmp_path / "longo.pdf"
    canvas = rl_canvas.Canvas(str(path), pagesize=(300, 400))
    for number in range(1, 61):
        canvas.drawString(50, 350, f"Pagina {number}")
        canvas.showPage()
    canvas.save()
    return path


def _viewer(path, layout: str | None = None) -> PdfViewer:
    _app()
    session = DocumentSession()
    viewer = PdfViewer(session, AnnotationState(), RedactionState())
    viewer.resize(900, 700)
    viewer.show()
    if layout:
        viewer.set_layout(layout)
    session.open(str(path))
    QApplication.processEvents()
    return viewer


def test_a_heavy_page_shows_at_once_and_sharpens_when_the_render_arrives(long_pdf):
    # Antes, cada página nova parava a janela o tempo do render (100-300 ms numa planta).
    viewer = _viewer(long_pdf)
    viewer._render_cost = 1.0  # o documento se mostrou pesado: nada cabe no tempo da tela
    label = viewer._page_labels[0]

    viewer._show_single_page(10)

    assert viewer._current_page == 10
    key = viewer._render_key(10)
    assert key not in viewer._pixmaps  # ainda não renderizada: um papel em branco no lugar
    assert logical_size(label.pixmap()) == viewer._placeholder_pixmap(10, None).deviceIndependentSize().toSize()
    assert _wait(lambda: key in viewer._pixmaps)
    QApplication.processEvents()
    assert label.pixmap().cacheKey() != 0 and viewer._pixmaps.get(key).size() == label.pixmap().size()
    viewer.close_document()


def test_the_next_page_is_ready_before_the_reader_gets_there(long_pdf):
    viewer = _viewer(long_pdf)
    viewer._show_single_page(3)

    assert _wait(lambda: viewer._render_key(4) in viewer._pixmaps and viewer._render_key(2) in viewer._pixmaps)
    viewer.close_document()


def test_redrawing_marks_over_a_page_does_not_render_it_again(long_pdf, monkeypatch):
    viewer = _viewer(long_pdf)
    renders = []
    original = viewer._render_now
    monkeypatch.setattr(viewer, "_render_now", lambda index: renders.append(index) or original(index))

    viewer._refresh_current_render()
    viewer._refresh_current_render()

    assert renders == []  # a página veio do cache, só as marcações foram redesenhadas
    viewer.close_document()


def test_continuous_mode_renders_heavy_pages_in_the_background(long_pdf):
    viewer = _viewer(long_pdf, CONTINUOUS)
    viewer._render_cost = 1.0
    viewer._scroll_to_page(30)
    QApplication.processEvents()

    assert 30 not in viewer._rendered_pages  # nada renderizado na thread da interface
    assert _wait(lambda: 30 in viewer._rendered_pages and 31 in viewer._rendered_pages)
    viewer.close_document()


def test_zoom_in_continuous_mode_keeps_the_old_image_until_the_new_one_arrives(long_pdf):
    viewer = _viewer(long_pdf, CONTINUOUS)
    assert 0 in viewer._rendered_pages
    viewer._render_cost = 1.0
    width = viewer._page_labels[0].pixmap().width()

    viewer._zoom_in()

    label = viewer._page_labels[0]
    assert label.pixmap() is not None and not label.pixmap().isNull()  # não ficou em branco
    assert label.sizeHint().width() == pytest.approx(label.width(), abs=1)  # esticada até a página nova
    assert viewer._render_key(0) not in viewer._pixmaps and width > 0
    assert _wait(lambda: 0 in viewer._rendered_pages)
    viewer.close_document()


def test_results_of_a_closed_document_are_dropped(long_pdf, tmp_path):
    _app()
    renderer = PageRenderer()
    received = []
    renderer.rendered.connect(lambda key, image, info: received.append(renderer.accept(key)))
    document = pdfium.PdfDocument(str(long_pdf))
    renderer.set_document(document)
    renderer.request(("page", 0), 0, 1.0, 1.0)
    assert _wait(renderer.is_idle)
    with PDFIUM_LOCK:
        renderer.set_document(None)  # o que já chegou deste documento não vale mais
        document.close()
    QApplication.processEvents()

    assert received in ([("page", 0)], [None])
    renderer.request(("page", 1), 1, 1.0, 1.0)  # sem documento: nada a fazer
    assert renderer.pending() == 0
    renderer.stop()


def test_pixmap_cache_keeps_the_most_recent_pages_within_its_budget():
    _app()
    from PySide6.QtGui import QPixmap

    page = QPixmap(100, 100)  # 40 KB em 32 bits
    cache = PixmapCache(budget=page.width() * page.height() * 4 * 3)
    for index in range(5):
        cache.put(index, QPixmap(page))
    cache.get(2)  # usada agora: fica
    cache.put(5, QPixmap(page))

    assert 2 in cache and 5 in cache and 0 not in cache and len(cache) == 3


def test_only_the_thumbnails_in_view_are_rendered(long_pdf):
    # Antes as 60 miniaturas eram renderizadas ao abrir, na thread da interface.
    viewer = _viewer(long_pdf)
    thumbnails = viewer.thumbnail_list
    viewer.show_side_panel(True)
    QApplication.processEvents()

    assert _wait(lambda: thumbnails.thumbnail(0) is not None)
    assert _wait(lambda: _rendering_done(viewer))
    assert thumbnails.thumbnail(59) is None and thumbnails.pending_count() > 30

    thumbnails.scrollToBottom()
    assert _wait(lambda: thumbnails.thumbnail(59) is not None)
    viewer.close_document()


def test_page_sizes_come_from_pdfium_without_opening_the_pages(tmp_path):
    writer = PdfWriter()
    for rotation, crop in ((0, None), (90, None), (270, (50, 60, 400, 700))):
        page = writer.add_blank_page(595, 842)
        if rotation:
            page.rotate(rotation)
        if crop:
            page.cropbox = RectangleObject(crop)
    path = tmp_path / "girado.pdf"
    writer.write(str(path))
    viewer = _viewer(path)
    document = pdfium.PdfDocument(str(path))

    for index in range(3):
        geometry = PageGeometry.from_pdfium_page(document[index])
        viewer._geometries.pop(index, None)  # como se a página ainda não tivesse sido aberta
        assert viewer._visual_size(index) == pytest.approx((geometry.width, geometry.height))
    document.close()
    viewer.close_document()


def test_document_details_arrive_after_the_first_page(tmp_path):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(300, 400)
    writer.add_outline_item("Capítulo", 1)
    writer.add_attachment("notas.txt", b"anexo")
    path = tmp_path / "com_sumario.pdf"
    writer.write(str(path))

    viewer = _viewer(path)
    assert viewer._page_labels[0].pixmap() is not None  # a página não esperou a leitura

    assert viewer.wait_for_details()
    assert viewer.side_panel.outline_tree.topLevelItem(0).text(0) == "Capítulo"
    assert viewer.side_panel.attachments_list.count() == 1
    viewer.close_document()


def test_the_window_opens_without_loading_the_pdf_libraries():
    # pypdf, reportlab, PIL e cryptography somavam ~1,3 s da abertura a frio, antes de haver
    # um PDF para ler. Só a aba de documento os usa, e ela é importada ao abrir o primeiro.
    import subprocess
    import sys

    code = (
        "import sys; import main; "
        "print(sorted(m for m in ('pypdf', 'reportlab.pdfgen', 'PIL.Image', 'cryptography', "
        "'ui.document_tab') if m in sys.modules))"
    )
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_closing_the_app_while_a_thread_renders_does_not_crash(tmp_path):
    # O pypdfium2 fecha documentos e páginas e destrói a biblioteca ao sair, sem lock: com a
    # thread de render (ou a dos recentes) no meio de uma página, o processo lia memória
    # liberada — violação de acesso, ou abortava ao fechar o app.
    import random
    import subprocess
    import sys

    heavy = tmp_path / "planta.pdf"  # uma página que leva dezenas de ms para renderizar
    canvas = rl_canvas.Canvas(str(heavy), pagesize=(595, 842))
    rng = random.Random(1)
    for _ in range(20000):
        x, y = rng.uniform(0, 595), rng.uniform(0, 842)
        canvas.line(x, y, x + rng.uniform(-30, 30), y + rng.uniform(-30, 30))
    canvas.save()
    code = (
        "import sys, threading, time\n"
        "import core.base\n"
        "import pypdfium2 as pdfium\n"
        "from core.progress import PDFIUM_LOCK\n"
        "def loop():\n"
        "    while True:\n"
        "        with PDFIUM_LOCK:\n"
        "            doc = pdfium.PdfDocument(sys.argv[1]); page = doc[0]\n"
        "            page.render(scale=2).close(); page.close(); doc.close()\n"
        "threading.Thread(target=loop, daemon=True).start()\n"
        "time.sleep(0.3)\n"
    )
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", code, str(heavy)], capture_output=True, text=True, cwd=root, timeout=120
        )
        assert result.returncode == 0 and "Traceback" not in result.stderr, result.stderr


def test_shared_reader_reads_the_file_once_and_gives_the_same_results(tmp_path, monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.add_outline_item("Um", 0)
    path = str(tmp_path / "doc.pdf")
    writer.write(path)
    plain = read_details(path)  # já usa o leitor compartilhado
    import pypdf

    readers = []
    original = pypdf.PdfReader
    monkeypatch.setattr(pypdf, "PdfReader", lambda source: readers.append(source) or original(source))

    with shared_reader(path):
        first = open_reader(path, purpose=base.READ)
        second = open_reader(path, purpose=base.READ)
    assert first is second and len(readers) == 1
    assert not isinstance(readers[0], str)  # um arquivo aberto, lido sob demanda

    again = read_details(path)
    assert [item.title for item in again.outline] == [item.title for item in plain.outline] == ["Um"]
    open_reader(path, purpose=base.READ)  # fora do bloco, como antes
    assert readers[-1] == path
