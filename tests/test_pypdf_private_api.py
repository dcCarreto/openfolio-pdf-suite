"""A API privada do pypdf fica só em core/base.py: um upgrade que a mude quebra um lugar só."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = re.compile(r"\b(?:writer|reader)\._[a-z]\w*")


def test_private_pypdf_calls_go_through_core_base():
    allowed = {ROOT / "core" / "base.py"}
    offenders = [
        f"{path.relative_to(ROOT)}: {match.group()}"
        for folder in ("core", "ui", "tests")
        for path in sorted((ROOT / folder).rglob("*.py"))
        if path not in allowed
        for match in PRIVATE.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
