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
