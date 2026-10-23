"""Fixtures compartilhadas pelos testes."""

import os
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas as rl_canvas

# Layouts de página em que a conversão de coordenadas costumava falhar (rotação, CropBox
# deslocada, MediaBox com origem fora de (0, 0)). Os testes de redação, edição, OCR e do
# visualizador rodam sobre todos eles, não só sobre a página "normal".
HARD_PAGE_LAYOUTS = {
    "normal": {},
    "rot90": {"rotate": 90},
    "rot180": {"rotate": 180},
    "rot270": {"rotate": 270},
    "cropbox": {"cropbox": (0, 200, 612, 792)},
    "origem_negativa_rot90": {
        "mediabox": (-40, -60, 640, 820),
        "cropbox": (20, 150, 600, 790),
        "rotate": 90,
    },
}


def require_program(path: str | None, name: str) -> None:
    """Testes com o programa de verdade (hoje o Tesseract): sem ele, o teste é pulado. No CI,
    onde ele é instalado (OPENFOLIO_REQUIRE_PROGRAMS=1), a falta dele reprova, para o teste
    não passar despercebido como pulado."""
    if path:
        return
    if os.environ.get("OPENFOLIO_REQUIRE_PROGRAMS"):
        pytest.fail(f"{name} não foi encontrado, mas OPENFOLIO_REQUIRE_PROGRAMS está ligado")
    pytest.skip(f"{name} não está instalado nesta máquina")


@pytest.fixture
def make_pdf(tmp_path):
    """Cria um PDF com páginas de tamanhos distintos, para permitir identificá-las depois."""

    def _make_pdf(name: str, page_sizes: list[tuple[int, int]]) -> Path:
        writer = PdfWriter()
        for width, height in page_sizes:
            writer.add_blank_page(width=width, height=height)
        path = tmp_path / name
        with open(path, "wb") as f:
            writer.write(f)
        return path

    return _make_pdf


@pytest.fixture
def make_encrypted_pdf(make_pdf):
    """Cria um PDF protegido por senha, para testar a recusa de PDFs de entrada criptografados."""

    def _make_encrypted_pdf(
        name: str, page_sizes: list[tuple[int, int]], password: str = "segredo123"
    ) -> Path:
        plain_path = make_pdf(f"_plain_{name}", page_sizes)
        writer = PdfWriter(clone_from=str(plain_path))
        writer.encrypt(user_password=password, algorithm="AES-256")
        path = plain_path.parent / name
        with open(path, "wb") as f:
            writer.write(f)
        return path

    return _make_encrypted_pdf


@pytest.fixture
def make_text_pdf(tmp_path):
    """Cria um PDF de uma página com textos em posições conhecidas do espaço do usuário e,
    opcionalmente, MediaBox/CropBox próprias e `/Rotate` (ver HARD_PAGE_LAYOUTS)."""

    def _make_text_pdf(
        name: str,
        texts: list[tuple[float, float, str]],
        *,
        pagesize: tuple[float, float] = (612, 792),
        mediabox=None,
        cropbox=None,
        rotate: int = 0,
        font_size: float = 20,
    ) -> Path:
        source = tmp_path / f"_src_{name}"
        canvas = rl_canvas.Canvas(str(source), pagesize=pagesize)
        canvas.setFont("Helvetica-Bold", font_size)
        for x, y, text in texts:
            canvas.drawString(x, y, text)
        canvas.showPage()
        canvas.save()

        writer = PdfWriter(clone_from=str(source))
        page = writer.pages[0]
        if mediabox is not None:
            page.mediabox = RectangleObject(mediabox)
        if cropbox is not None:
            page.cropbox = RectangleObject(cropbox)
        if rotate:
            page.rotate(rotate)
        path = tmp_path / name
        with open(path, "wb") as f:
            writer.write(f)
        return path

    return _make_text_pdf


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """Um diálogo modal aberto por `exec()` travaria a suíte (no modo offscreen ninguém o
    fecha): os testes que querem conferir um diálogo o substituem explicitamente."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)
