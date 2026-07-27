"""Testes de core/ocr.py.

O Tesseract é um binário externo (pode não estar instalado em toda máquina que roda os
testes), então a lógica de posicionamento/decisão é testada com `_run_tesseract`
substituído (monkeypatch) por dados simulados, e a detecção do binário é testada
sobrescrevendo `_TESSERACT_CANDIDATES` em vez de depender do que está instalado de verdade.
"""

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas as rl_canvas

from core import ocr
from core.base import EncryptedPDFError


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


def test_find_tesseract_finds_a_direct_file_path(monkeypatch, tmp_path):
    fake_binary = tmp_path / "tesseract.exe"
    fake_binary.write_text("fake")
    monkeypatch.setattr(ocr, "_TESSERACT_CANDIDATES", [str(fake_binary)])
    assert ocr.find_tesseract() == str(fake_binary)


def test_get_available_languages_returns_empty_when_tesseract_missing(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert ocr.get_available_languages() == []


def test_get_available_languages_excludes_osd(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr.pytesseract, "get_languages", lambda config: ["eng", "osd", "por"])
    assert ocr.get_available_languages() == ["eng", "por"]


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
