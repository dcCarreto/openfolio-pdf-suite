"""Versão única (core/version.py) e Ajuda > Sobre (ui/about_dialog.py)."""

from importlib import metadata
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from core.version import APP_VERSION
from ui.about_dialog import AboutDialog, python_components

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_the_version_is_the_one_in_pyproject():
    tomllib = pytest.importorskip("tomllib")
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        assert APP_VERSION == tomllib.load(f)["project"]["version"]


def test_python_components_are_the_runtime_dependencies_with_their_licenses():
    components = {name.lower(): (version, license) for name, version, license in python_components()}

    assert components["pypdf"] == (metadata.version("pypdf"), "BSD-3-Clause")
    assert "pyside6" in components and "pillow" in components
    assert "lxml" in components  # indireta, via python-docx
    assert "openfolio-pdf-suite" not in components
    assert "pytest" not in components and "ruff" not in components  # só de teste e de lint


def _rows(dialog):
    table = dialog.components_table
    return [tuple(table.item(row, column).text() for column in range(3)) for row in range(table.rowCount())]


def test_about_shows_the_version_the_log_file_and_the_components(tmp_path):
    QApplication.instance() or QApplication([])
    log_file = tmp_path / "openfolio.log"

    dialog = AboutDialog(log_file)

    assert dialog.log_edit.text() == str(log_file)
    rows = _rows(dialog)
    assert ("Tesseract OCR", "5", "Apache-2.0") in rows
    assert any(name == "pypdf" for name, _version, _license in rows)
    assert APP_VERSION not in dialog.header.text()  # o usuário não vê número de versão
    assert "CHANGELOG.md" in dialog.header.text()


def test_about_without_a_log_file_disables_open_folder():
    QApplication.instance() or QApplication([])

    dialog = AboutDialog(None)

    assert dialog.log_edit.text() == "(sem arquivo de log)"
    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Abrir pasta")
    assert not button.isEnabled()
