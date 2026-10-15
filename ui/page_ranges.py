"""Leitura de listas de páginas digitadas pelo usuário ("1-3, 5, 8-").

A interface conta páginas a partir de 1, como o visualizador e as miniaturas mostram; as
operações de `core/` recebem índices a partir de 0. A conversão acontece só aqui.
"""

import re

_TOKEN = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d*)\s*)?$")


def parse_page_ranges(text: str, total_pages: int | None = None) -> list[int]:
    """Converte "1-3, 5, 8-" em índices a partir de 0, na ordem digitada.

    - "N-M" com N maior que M vale de trás para frente ("4-1" é 4, 3, 2, 1).
    - "N-" vai até a última página (exige `total_pages`).
    - Página 0 ou acima de `total_pages` é erro, com mensagem para o usuário.
    """
    pages: list[int] = []
    for raw_token in text.split(","):
        token = raw_token.strip()
        if not token:
            continue
        match = _TOKEN.match(token)
        if match is None:
            raise ValueError(f'Não entendi "{token}". Use números e intervalos, como 1, 3-5 ou 8-.')
        start = int(match.group(1))
        if match.group(2) is None:
            end = start
        elif match.group(2) == "":
            if total_pages is None:
                raise ValueError(f'"{token}" precisa saber quantas páginas o documento tem.')
            end = total_pages
        else:
            end = int(match.group(2))
        for page in (start, end):
            if page < 1:
                raise ValueError("As páginas começam em 1.")
            if total_pages is not None and page > total_pages:
                raise ValueError(f"A página {page} não existe: o documento tem {total_pages} página(s).")
        step = 1 if end >= start else -1
        pages.extend(index - 1 for index in range(start, end + step, step))
    return pages
