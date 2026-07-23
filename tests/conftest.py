"""Fixtures compartilhadas pelos testes."""

from pathlib import Path

import pytest
from pypdf import PdfWriter


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
