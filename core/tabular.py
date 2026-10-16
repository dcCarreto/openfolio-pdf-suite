"""Exportação de tabelas (comentários, dados de formulário) para CSV ou Excel.

- CSV em UTF-8 com BOM: sem o BOM, o Excel em português abre os acentos quebrados.
- `.xlsx` (pelo nome do arquivo): o Excel em português espera ";" num CSV e mostra tudo numa
  coluna só quando recebe ","; a planilha abre certa em qualquer idioma.
- Valores que começam com "=", "+", "-", "@" ou tabulação viram fórmula ao abrir no Excel
  ("CSV injection"). Como os textos vêm de PDFs de terceiros (um comentário pode conter
  `=HYPERLINK(...)`), eles saem com um apóstrofo na frente no CSV e como texto na planilha.
"""

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from .base import atomic_output

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_formula(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def write_table(output_path: str, header: Sequence[str], rows: Iterable[Sequence]) -> None:
    """Grava `header` e `rows` em CSV ou, se `output_path` terminar em .xlsx, em Excel."""
    if Path(output_path).suffix.lower() == ".xlsx":
        _write_xlsx(output_path, header, rows)
        return
    with atomic_output(output_path) as temp_path:
        with open(temp_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                writer.writerow([value if isinstance(value, (int, float)) else escape_formula(value) for value in row])


def _write_xlsx(output_path: str, header: Sequence[str], rows: Iterable[Sequence]) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(header))
    for row in rows:
        sheet.append([value if isinstance(value, (int, float)) else ("" if value is None else str(value)) for value in row])
    for cells in sheet.iter_rows(min_row=2):
        for cell in cells:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # texto, nunca fórmula
    with atomic_output(output_path) as temp_path:
        workbook.save(temp_path)
