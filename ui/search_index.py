"""Um índice só para as duas buscas (a paleta de comandos e o campo da aba Ferramentas): as
ferramentas e os modos delas, com os sinônimos ("cpf" acha Redigir e limpar, "word" acha
Converter) e os nomes antigos das ferramentas ("Assinatura digital", "Extrair texto").

Cada palavra digitada precisa ser o começo de uma palavra do nome, da descrição ou de um
sinônimo ("word" acha Converter, não o "password" de Senha e permissões). Quando só um sinônimo
explica o resultado, a busca diz qual foi: "por “assinatura”".
"""

import re
import unicodedata
from dataclasses import dataclass

from ui.i18n import tr
from ui.tools import SYNONYMS, TOOLS, Tool, page_synonyms


def fold_text(text: str) -> str:
    """Minúsculas sem acento, para "acoes" achar "Ações"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", fold_text(text))


@dataclass
class Entry:
    tool: Tool
    mode: int | None  # None: a ferramenta inteira
    words: list[str]  # do nome e da descrição, no idioma atual e em português
    synonyms: list[str]

    @property
    def title(self) -> str:
        """"Converter" ou "Converter › Extrair texto"."""
        if self.mode is None:
            return tr(self.tool.title)
        return f"{tr(self.tool.title)} › {tr(self.tool.modes[self.mode].label)}"


def entries(with_modes: bool = True) -> list[Entry]:
    """As ferramentas (na ordem do registro) e, com `with_modes`, os modos das que têm mais de um.
    Sem `with_modes` (a aba Ferramentas), o nome dos modos leva à ferramenta; com eles (a
    paleta), leva só ao modo, que é o resultado mais exato."""
    result = []
    for tool in TOOLS.values():
        pages = {mode.page for mode in tool.modes}
        base = f"{tr(tool.title)} {tr(tool.description)} {tool.title} {tool.description}"
        synonyms = " ".join([SYNONYMS.get(tool.id, ""), *(page_synonyms(page) for page in pages)])
        if not with_modes:
            synonyms += " " + " ".join(f"{tr(mode.label)} {mode.label}" for mode in tool.modes)
        result.append(Entry(tool, None, _words(base), _words(synonyms)))
        if with_modes and len(tool.modes) > 1:
            for index, mode in enumerate(tool.modes):
                text = f"{tr(tool.title)} {tr(mode.label)} {tool.title} {mode.label}"
                result.append(Entry(tool, index, _words(text), _words(page_synonyms(mode.page))))
    return result


def in_title(entry: Entry, query: str) -> bool:
    """Cada palavra digitada começa uma palavra do nome mostrado ("Preencher e assinar ›
    Certificado digital"): o resultado mais exato, que a paleta destaca."""
    title = _words(entry.title)
    typed = _words(query)
    return bool(typed) and all(any(candidate.startswith(word) for candidate in title) for word in typed)


def match(entry: Entry, query: str) -> tuple[bool, str]:
    """(achou, motivo): o motivo é o sinônimo que explica o resultado, ou "" se o nome ou a
    descrição bastam."""
    typed = _words(query)
    reason = ""
    for word in typed:
        if any(candidate.startswith(word) for candidate in entry.words):
            continue
        synonym = next((candidate for candidate in entry.synonyms if candidate.startswith(word)), None)
        if synonym is None:
            return False, ""
        reason = reason or synonym
    return True, reason
