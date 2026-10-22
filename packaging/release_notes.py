"""Imprime o trecho do CHANGELOG.md de uma atualização, para as notas da release (que o app
mostra ao usuário antes de ele aceitar instalar).

    python packaging/release_notes.py 2026.10.21

O identificador é a data da atualização (a versão do pyproject.toml, sem zeros à esquerda:
2026.11.3); o trecho é o que vem depois do título com a mesma data ("## 2026-11-03") até o
próximo "## ". Sem o trecho, ou com ele vazio, sai com erro: uma atualização não é publicada
sem dizer o que mudou.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def _numbers(text: str) -> tuple[int, ...] | None:
    return tuple(int(part) for part in re.split(r"[.-]", text)) if re.fullmatch(r"\d+([.-]\d+)*", text) else None


def notes_for(identifier: str, changelog: str) -> str | None:
    wanted = _numbers(identifier)
    lines = changelog.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ") and _numbers(line[3:].strip()) == wanted]
    if wanted is None or not starts:
        return None
    start = starts[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip() or None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("uso: python packaging/release_notes.py AAAA.MM.DD", file=sys.stderr)
        return 2
    notes = notes_for(argv[0], CHANGELOG.read_text(encoding="utf-8"))
    if notes is None:
        print(f'O CHANGELOG.md não tem o que mudou na atualização {argv[0]} (título "## AAAA-MM-DD").', file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
