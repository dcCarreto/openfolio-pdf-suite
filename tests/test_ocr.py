"""Testes de core/ocr.py.

O Tesseract é um binário externo (pode não estar instalado em toda máquina que roda os
testes), então a lógica de posicionamento/decisão é testada com `_run_tesseract`
substituído (monkeypatch) por dados simulados, e a detecção do binário é testada
sobrescrevendo `_TESSERACT_CANDIDATES` em vez de depender do que está instalado de verdade.
"""

import io
import os
import sys

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from core import ocr
from core.base import EncryptedPDFError
from tests.conftest import require_program


def _make_pdf_with_text(path, text: str) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.setFont("Helvetica", 16)
    canvas.drawString(40, 250, text)
    canvas.showPage()
    canvas.save()


def _fake_ocr_data(words: list[tuple[str, int, int, int, int, int]]) -> dict:
    """words: lista de (texto, left_px, top_px, width_px, height_px, conf)."""
    return {
        "text": [w[0] for w in words],
        "left": [w[1] for w in words],
        "top": [w[2] for w in words],
        "width": [w[3] for w in words],
        "height": [w[4] for w in words],
        "conf": [w[5] for w in words],
    }


def test_find_tesseract_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr(ocr, "_TESSERACT_CANDIDATES", ["um-binario-que-nao-existe-xyz"])
    assert ocr.find_tesseract() is None


def test_the_tesseract_bundled_with_the_app_comes_first(monkeypatch, tmp_path):
    bundled = tmp_path / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
    bundled.write_text("fake")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(ocr, "_TESSERACT_CANDIDATES", [__file__])  # um "instalado" que não deve ganhar
    monkeypatch.setenv("TESSDATA_PREFIX", "idiomas de outro Tesseract")

    assert ocr.find_tesseract() == str(bundled)
    assert os.environ["TESSDATA_PREFIX"] == str(tmp_path / "tessdata")


def test_without_the_bundled_copy_an_installed_tesseract_is_used(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)  # app empacotado sem a cópia
    monkeypatch.setattr(ocr, "_TESSERACT_CANDIDATES", [__file__])

    assert ocr.find_tesseract() == __file__


def test_find_tesseract_finds_a_direct_file_path(monkeypatch, tmp_path):
    fake_binary = tmp_path / "tesseract.exe"
    fake_binary.write_text("fake")
    monkeypatch.setattr(ocr, "_TESSERACT_CANDIDATES", [str(fake_binary)])
    assert ocr.find_tesseract() == str(fake_binary)


def test_get_available_languages_returns_empty_when_tesseract_missing(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert ocr.get_available_languages() == []


@pytest.fixture(autouse=True)
def _fresh_language_cache():
    ocr._installed_languages.cache_clear()
    yield
    ocr._installed_languages.cache_clear()


def test_get_available_languages_excludes_osd(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr.pytesseract, "get_languages", lambda config: ["eng", "osd", "por"])
    assert ocr.get_available_languages() == ["eng", "por"]
    assert ocr.has_orientation_data()


def test_languages_are_asked_to_tesseract_only_once(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr.pytesseract, "get_languages", lambda config: calls.append(1) or ["por"])

    ocr.get_available_languages()
    ocr.get_available_languages()

    assert calls == [1]  # a aba de OCR não roda o Tesseract de novo a cada troca de idioma


def test_run_raises_when_tesseract_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    path = tmp_path / "doc.pdf"
    _make_pdf_with_text(path, "qualquer coisa")

    with pytest.raises(RuntimeError):
        ocr.OCRDocument().run(str(path), str(tmp_path / "out.pdf"))


def test_run_rejects_encrypted_input(monkeypatch, make_encrypted_pdf, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ocr.OCRDocument().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_run_skips_pages_that_already_have_text(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    called = []
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: called.append(1) or _fake_ocr_data([]))

    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "out.pdf"
    _make_pdf_with_text(path_in, "este pdf ja tem texto")

    pages_ocred = ocr.OCRDocument().run(str(path_in), str(path_out), skip_pages_with_text=True)

    assert pages_ocred == 0
    assert called == []  # OCR nem chegou a rodar: a página já tinha texto
    assert "este pdf ja tem texto" in PdfReader(str(path_out)).pages[0].extract_text()


def test_run_adds_searchable_text_to_pages_without_text(monkeypatch, tmp_path):
    # Simula uma página "escaneada": PdfReader.Page.extract_text() precisa retornar vazio
    # para o teste exercitar o caminho de OCR. Uma página em branco do pypdf serve bem.
    from pypdf import PdfWriter

    path_in = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=300)
    with open(path_in, "wb") as f:
        writer.write(f)

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    fake_words = _fake_ocr_data(
        [
            ("Hello", 200, 200, 150, 50, 96),
            ("", 0, 0, 0, 0, -1),  # linha de "bloco" vazia que o tesseract também retorna
            ("world", 400, 200, 100, 50, 92),
            ("lixo", 10, 10, 10, 10, 5),  # confiança baixa: deve ser descartado
        ]
    )
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: fake_words)

    path_out = tmp_path / "out.pdf"
    pages_ocred = ocr.OCRDocument().run(str(path_in), str(path_out), min_confidence=30)

    assert pages_ocred == 1
    extracted = PdfReader(str(path_out)).pages[0].extract_text()
    assert "Hello" in extracted
    assert "world" in extracted
    assert "lixo" not in extracted


def test_run_preserves_page_count(monkeypatch, tmp_path):
    from pypdf import PdfWriter

    path_in = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=300)
    writer.add_blank_page(width=400, height=300)
    with open(path_in, "wb") as f:
        writer.write(f)

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: _fake_ocr_data([]))

    path_out = tmp_path / "out.pdf"
    ocr.OCRDocument().run(str(path_in), str(path_out))

    assert len(PdfReader(str(path_out)).pages) == 2


@pytest.mark.parametrize(
    "layout",
    [{"rotate": 90}, {"rotate": 270}, {"rotate": 180}, {"cropbox": (30, 40, 380, 290)}],
    ids=["rot90", "rot270", "rot180", "cropbox"],
)
def test_invisible_text_lands_on_the_recognized_word_on_hard_pages(monkeypatch, tmp_path, layout):
    # O Tesseract devolve caixas em pixels da página como ela aparece na tela; o texto
    # invisível precisa cair ali — e correr na direção da leitura — mesmo em páginas giradas.
    import pypdfium2 as pdfium
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject

    from core.geometry import PageGeometry

    path_in = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    if "cropbox" in layout:
        page.cropbox = RectangleObject(layout["cropbox"])
    if layout.get("rotate"):
        page.rotate(layout["rotate"])
    with open(path_in, "wb") as f:
        writer.write(f)

    word_px = (200, 300, 360, 60)  # left, top, width, height na imagem renderizada
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(
        ocr, "_run_tesseract", lambda image, language: _fake_ocr_data([("Hello", *word_px, 95)])
    )

    path_out = tmp_path / "out.pdf"
    assert ocr.OCRDocument().run(str(path_in), str(path_out)) == 1

    document = pdfium.PdfDocument(str(path_out))
    try:
        pdf_page = document[0]
        geometry = PageGeometry.from_pdfium_page(pdf_page)
        textpage = pdf_page.get_textpage()
        assert textpage.get_text_range().strip() == "Hello"
        boxes = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
        textpage.close()
    finally:
        document.close()

    user_box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    left, bottom, right, top = geometry.user_rect_to_visual(user_box)
    scale = ocr._OCR_SCALE
    word_left, word_top = word_px[0] / scale, geometry.height - word_px[1] / scale
    word_bottom = word_top - word_px[3] / scale
    # A caixa do caractere mede a tinta do glifo; com a palavra esticada na largura da
    # imagem (Tz), o recuo lateral do "H" também estica um pouco.
    assert left == pytest.approx(word_left, abs=4)
    assert word_bottom - 3 <= bottom and top <= word_top + 3
    assert right - left > top - bottom  # a palavra corre na horizontal, como na tela



def _blank_pdf(path, pages=1, size=(400, 300)):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=size[0], height=size[1])
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _char_boxes(path):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        textpage = document[0].get_textpage()
        boxes = [textpage.get_charbox(i, loose=True) for i in range(textpage.count_chars())]
        text = textpage.get_text_range()
        textpage.close()
    finally:
        document.close()
    return text, boxes


def test_invisible_word_spans_the_recognized_width(monkeypatch, tmp_path):
    # Sem a escala horizontal (Tz), "Hi" ficava bem mais estreito que a palavra na imagem
    # e a seleção não cobria o que aparece na tela.
    path_in = _blank_pdf(tmp_path / "scan.pdf")
    word_px = (100, 100, 600, 50)  # palavra larga: 144 pt
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: _fake_ocr_data([("Hi", *word_px, 90)]))
    path_out = tmp_path / "out.pdf"

    ocr.OCRDocument().run(str(path_in), str(path_out))

    text, boxes = _char_boxes(path_out)
    assert text.strip() == "Hi"
    left, right = min(b[0] for b in boxes), max(b[2] for b in boxes)
    expected_width = word_px[2] / ocr._OCR_SCALE
    assert right - left == pytest.approx(expected_width, rel=0.1)


def _scan_with_stamp(path, stamp_text="PROTOCOLO 123"):
    """Página "escaneada" (uma imagem cobrindo a página) com um carimbo de texto por cima."""
    import io

    from PIL import Image
    from reportlab.lib.utils import ImageReader

    buffer = io.BytesIO()
    Image.new("L", (400, 300), 230).save(buffer, format="PNG")
    buffer.seek(0)
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.drawImage(ImageReader(buffer), 0, 0, 400, 300)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(300, 280, stamp_text)
    canvas.showPage()
    canvas.save()
    return path


def test_scanned_page_with_a_text_stamp_still_gets_ocr(monkeypatch, tmp_path):
    path_in = _scan_with_stamp(tmp_path / "scan.pdf")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(
        ocr, "_run_tesseract", lambda image, language: _fake_ocr_data([("Contrato", 100, 400, 300, 50, 90)])
    )
    path_out = tmp_path / "out.pdf"

    assert ocr.OCRDocument().run(str(path_in), str(path_out)) == 1

    text = PdfReader(str(path_out)).pages[0].extract_text()
    assert "Contrato" in text and "PROTOCOLO" in text


def test_page_with_real_text_is_skipped_in_auto_mode_but_not_in_force_mode(monkeypatch, tmp_path):
    path_in = tmp_path / "texto.pdf"
    _make_pdf_with_text(path_in, "texto de verdade " * 20)
    calls = []
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: calls.append(language) or _fake_ocr_data([]))

    ocr.OCRDocument().run(str(path_in), str(tmp_path / "auto.pdf"), mode="auto")
    assert calls == []
    ocr.OCRDocument().run(str(path_in), str(tmp_path / "force.pdf"), mode="force", language="por+eng")
    assert calls == ["por+eng"]  # vários idiomas vão juntos para o Tesseract


def test_dpi_controls_the_rendered_image(monkeypatch, tmp_path):
    path_in = _blank_pdf(tmp_path / "scan.pdf")
    sizes = []
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: sizes.append(image.size) or _fake_ocr_data([]))

    ocr.OCRDocument().run(str(path_in), str(tmp_path / "out.pdf"), dpi=144)

    assert sizes == [(800, 600)]


@pytest.mark.parametrize("kwargs", [{"dpi": 20}, {"mode": "sempre"}, {"language": ""}, {"language": "por+"}])
def test_invalid_options_are_rejected(monkeypatch, tmp_path, kwargs):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")

    with pytest.raises(ValueError):
        ocr.OCRDocument().run(str(_blank_pdf(tmp_path / "scan.pdf")), str(tmp_path / "out.pdf"), **kwargs)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_sideways_scan_text_follows_the_lines_in_the_image(monkeypatch, tmp_path, rotation):
    # Página digitalizada de lado: o Tesseract recebe a imagem já de pé, e o texto
    # invisível precisa voltar para onde a palavra está na imagem original, na direção dela.
    path_in = _blank_pdf(tmp_path / "scan.pdf", size=(400, 400))
    image_side = round(400 * ocr._OCR_SCALE)
    received = []

    def fake_tesseract(image, language):
        received.append(image.size)
        return _fake_ocr_data([("Palavra", 300, 200, 600, 80, 90)])  # no canto superior esquerdo da imagem de pé

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_detect_rotation", lambda image: rotation)
    monkeypatch.setattr(ocr, "_run_tesseract", fake_tesseract)
    path_out = tmp_path / "out.pdf"

    ocr.OCRDocument().run(str(path_in), str(path_out), detect_orientation=True)

    assert received == [(image_side, image_side)]
    _text, boxes = _char_boxes(path_out)
    left, bottom = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, top = max(b[2] for b in boxes), max(b[3] for b in boxes)

    # Onde a palavra (x 300..900, y 200..280 na imagem de pé) fica na página, em pontos PDF.
    scale = ocr._OCR_SCALE
    s_ = image_side
    expected = {
        90: ((200, 280), (300, 900)),
        180: ((s_ - 900, s_ - 300), (200, 280)),
        270: ((s_ - 280, s_ - 200), (s_ - 900, s_ - 300)),
    }[rotation]
    (x0, x1), (y0, y1) = expected
    assert (left + right) / 2 == pytest.approx((x0 + x1) / 2 / scale, abs=8)
    assert (bottom + top) / 2 == pytest.approx((y0 + y1) / 2 / scale, abs=8)
    if rotation == 180:
        assert right - left > top - bottom
    else:
        assert top - bottom > right - left  # a linha corre na vertical da página


def _scan_image_pdf(path, size=(400, 300), lines=(), skew=0.0):
    """Página "escaneada": uma imagem cobrindo a página, com `lines` escritas e girada `skew`
    graus (anti-horário), como uma folha torta no scanner."""
    from PIL import Image, ImageDraw

    scale = ocr._OCR_SCALE
    image = Image.new("L", (round(size[0] * scale), round(size[1] * scale)), 255)
    draw = ImageDraw.Draw(image)
    for index, _line in enumerate(lines):
        top = 150 + 120 * index
        draw.rectangle((120, top, image.width - 120, top + 50), fill=0)  # uma "linha de texto"
    if skew:
        image = image.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=255)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    canvas = rl_canvas.Canvas(str(path), pagesize=size)
    canvas.drawImage(ImageReader(buffer), 0, 0, *size)
    canvas.showPage()
    canvas.save()
    return path


def test_redo_replaces_a_previous_ocr_layer(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    word = [("Velho", 100, 100, 300, 50, 90)]
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: _fake_ocr_data(word))
    first, second = tmp_path / "primeiro.pdf", tmp_path / "refeito.pdf"
    ocr.OCRDocument().run(str(_scan_image_pdf(tmp_path / "scan.pdf")), str(first))

    word[:] = [("Novo", 100, 100, 300, 50, 90)]
    assert ocr.OCRDocument().run(str(first), str(second), mode="redo") == 1

    text = PdfReader(str(second)).pages[0].extract_text()
    assert "Novo" in text and "Velho" not in text
    assert len(PdfReader(str(second)).pages[0].images) == 1  # a imagem escaneada continua


def test_redo_keeps_pages_with_real_text(monkeypatch, tmp_path):
    path_in = tmp_path / "texto.pdf"
    _make_pdf_with_text(path_in, "Contrato assinado em duas vias pelas partes")
    calls = []
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: calls.append(1) or _fake_ocr_data([]))

    assert ocr.OCRDocument().run(str(path_in), str(tmp_path / "out.pdf"), mode="redo") == 0

    assert calls == []
    assert "Contrato" in PdfReader(str(tmp_path / "out.pdf")).pages[0].extract_text()


def test_removing_invisible_text_keeps_visible_text_and_its_font(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import ContentStream

    path = tmp_path / "base.pdf"
    _make_pdf_with_text(path, "x")  # só para ter a fonte /F1 nos recursos
    writer = PdfWriter(clone_from=str(path))
    page = writer.pages[0]
    # O segundo bloco usa a fonte escolhida no primeiro, o invisível.
    raw = b"BT /F1 16 Tf 3 Tr 40 200 Td (oculto) Tj ET BT 0 Tr 40 100 Td (visivel) Tj ET"
    stream = ContentStream(None, writer)
    stream.set_data(raw)
    page.replace_contents(stream)

    assert ocr.remove_invisible_text(page, writer) is True

    output = tmp_path / "out.pdf"
    writer.write(output)
    assert PdfReader(str(output)).pages[0].extract_text().strip() == "visivel"
    _text, boxes = _char_boxes(output)
    assert len(boxes) == len("visivel")  # o pdfium desenha o visível, com a fonte certa
    assert ocr.remove_invisible_text(PdfWriter(clone_from=str(output)).pages[0], writer) is False


def test_straighten_puts_a_sideways_page_upright(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "_detect_rotation", lambda image: 90)
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: _fake_ocr_data([("Palavra", 300, 200, 600, 80, 90)]))
    path_in = _scan_image_pdf(tmp_path / "scan.pdf", size=(400, 400))
    plain, straight = tmp_path / "sem.pdf", tmp_path / "com.pdf"

    ocr.OCRDocument().run(str(path_in), str(plain), detect_orientation=True)
    ocr.OCRDocument().run(str(path_in), str(straight), detect_orientation=True, straighten=True)

    assert PdfReader(str(plain)).pages[0].rotation == 0
    assert PdfReader(str(straight)).pages[0].rotation == 90
    assert _char_boxes(straight) == _char_boxes(plain)  # o texto continua sobre a palavra


def test_straighten_deskews_the_page_before_reading_it(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    received = []
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image, language: received.append(image) or _fake_ocr_data([]))
    path_in = _scan_image_pdf(tmp_path / "torto.pdf", lines=range(6), skew=3)
    path_out = tmp_path / "out.pdf"
    scale = ocr._OCR_SCALE

    ocr.OCRDocument().run(str(path_in), str(path_out))
    assert ocr._skew(received[-1], scale) == pytest.approx(-3, abs=0.3)  # sem endireitar: torta

    ocr.OCRDocument().run(str(path_in), str(path_out), straighten=True)
    assert ocr._skew(received[-1], scale) == 0.0  # o Tesseract recebe a página reta
    document = pdfium.PdfDocument(str(path_out))
    rendered = document[0].render(scale=scale).to_pil()
    document.close()
    assert ocr._skew(rendered, scale) == 0.0  # e o documento fica reto


# --- Com o Tesseract de verdade -------------------------------------------------------


_PARAGRAPH = [
    "The quick brown fox jumps over the",
    "lazy dog while the scanner keeps",
    "turning every page of the report",
    "into a picture without any text.",
]


def _scanned_pdf(path, lines: list[str], rotation: int = 0):
    """Um escaneado de verdade: o texto vira uma imagem de 300 DPI (sem texto no PDF),
    girada `rotation` graus como uma folha posta de lado no scanner."""
    source = path.with_name("origem.pdf")
    c = rl_canvas.Canvas(str(source), pagesize=(420, 300))
    c.setFont("Helvetica", 18)
    for index, line in enumerate(lines):
        c.drawString(30, 260 - 32 * index, line)
    c.save()
    document = pdfium.PdfDocument(str(source))
    image = document[0].render(scale=300 / 72).to_pil().convert("L")
    document.close()
    image = image.rotate(rotation, expand=True)
    width, height = (420, 300) if rotation % 180 == 0 else (300, 420)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    c = rl_canvas.Canvas(str(path), pagesize=(width, height))
    c.drawImage(ImageReader(buffer), 0, 0, width, height)
    c.save()
    return path


def test_real_tesseract_makes_a_scanned_page_searchable(tmp_path):
    require_program(ocr.find_tesseract(), "Tesseract")
    path_in = _scanned_pdf(tmp_path / "scan.pdf", ["OpenFolio reads scanned pages", "Invoice number 2026"])
    assert not PdfReader(str(path_in)).pages[0].extract_text().strip()
    path_out = tmp_path / "out.pdf"

    assert ocr.OCRDocument().run(str(path_in), str(path_out)) == 1

    text = PdfReader(str(path_out)).pages[0].extract_text()
    for word in ("OpenFolio", "scanned", "Invoice", "2026"):
        assert word in text


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_real_tesseract_reads_a_sideways_scan(tmp_path, rotation):
    require_program(ocr.find_tesseract() if ocr.has_orientation_data() else None, "Tesseract com o pacote osd")
    # A detecção de orientação do Tesseract recusa páginas com pouco texto ("Too few
    # characters"): um parágrafo, como numa folha de verdade.
    lines = ["OpenFolio reads sideways pages", *_PARAGRAPH]
    path_in = _scanned_pdf(tmp_path / "scan.pdf", lines, rotation=rotation)
    path_out = tmp_path / "out.pdf"

    assert ocr.OCRDocument().run(str(path_in), str(path_out), detect_orientation=True) == 1

    text = PdfReader(str(path_out)).pages[0].extract_text()
    for word in ("OpenFolio", "sideways", "pages"):
        assert word in text


def test_real_tesseract_redo_does_not_duplicate_the_text(tmp_path):
    require_program(ocr.find_tesseract(), "Tesseract")
    path_in = _scanned_pdf(tmp_path / "scan.pdf", ["OpenFolio reads scanned pages"])
    first, redone = tmp_path / "primeiro.pdf", tmp_path / "refeito.pdf"

    ocr.OCRDocument().run(str(path_in), str(first))
    assert ocr.OCRDocument().run(str(first), str(redone), mode="redo") == 1

    assert PdfReader(str(redone)).pages[0].extract_text().count("OpenFolio") == 1
