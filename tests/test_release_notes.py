"""packaging/release_notes.py: o texto de cada atualização sai do CHANGELOG.md."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Carregado pelo caminho: "packaging" também é o nome de um pacote do pip.
_spec = importlib.util.spec_from_file_location("release_notes", ROOT / "packaging" / "release_notes.py")
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

_CHANGELOG = """# O que mudou

## 2026-11-03

### Novidades

- Ferramenta nova

## 2026-10-21

- Primeira atualização

## 2026-10-01
"""


def test_the_section_of_the_update_is_extracted():
    assert release_notes.notes_for("2026.11.3".replace(".3", ".03"), _CHANGELOG) == "### Novidades\n\n- Ferramenta nova"
    assert release_notes.notes_for("2026.10.21", _CHANGELOG) == "- Primeira atualização"


def test_an_update_without_notes_is_refused():
    assert release_notes.notes_for("2026.12.1", _CHANGELOG) is None  # sem título
    assert release_notes.notes_for("2026.10.01", _CHANGELOG) is None  # título sem texto


def test_the_changelog_has_a_section_for_the_next_update():
    # Entre uma atualização e outra, a seção "Próxima atualização"; no commit da release (que
    # troca esse título pela data, ver RELEASING.md), as notas do identificador do pyproject.toml.
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = re.search(r'^version = "(.+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    assert version is not None
    assert "## Próxima atualização" in changelog or release_notes.notes_for(version.group(1), changelog)
