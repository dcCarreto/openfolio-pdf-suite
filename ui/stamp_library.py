"""Biblioteca de carimbos customizados (nome + texto + cor), persistida localmente via
`QSettings` — a forma idiomática do Qt de guardar preferências entre execuções, sem
precisar inventar um formato de arquivo próprio para algo tão simples.

Os carimbos ficam numa lista (`beginWriteArray`), não um grupo por nome: no QSettings, "/"
e "\\" num nome de grupo criam subgrupos, e um carimbo chamado "Aprovado/RH" sumia da
lista. Carimbos gravados no formato antigo (um grupo por nome) são lidos — inclusive os que
tinham "/" no nome — e passam para a lista na próxima gravação.
"""

from dataclasses import dataclass

from PySide6.QtCore import QSettings

_ORG = "OpenFolio"
_APP = "OpenFolioPDFSuite"
_LEGACY_GROUP = "custom_stamps"
_ARRAY = "stamp_library"
DEFAULT_STAMP_COLOR = "f44336"


@dataclass
class StampDefinition:
    name: str
    text: str
    color: str = DEFAULT_STAMP_COLOR


class StampLibrary:
    """Gerencia carimbos customizados salvos localmente. Aceita uma `QSettings` própria
    (ex.: apontando para um arquivo .ini temporário) para ser testável sem tocar nas
    preferências reais do usuário — sem argumento, usa as preferências reais do app."""

    def __init__(self, settings: QSettings | None = None):
        self._settings = settings or QSettings(_ORG, _APP)

    def list_stamps(self) -> list[StampDefinition]:
        stamps = {stamp.name: stamp for stamp in self._legacy_stamps()}
        size = self._settings.beginReadArray(_ARRAY)
        try:
            for index in range(size):
                self._settings.setArrayIndex(index)
                name = str(self._settings.value("name", ""))
                if name:
                    stamps[name] = StampDefinition(
                        name=name,
                        text=str(self._settings.value("text", "")),
                        color=str(self._settings.value("color", DEFAULT_STAMP_COLOR)),
                    )
        finally:
            self._settings.endArray()
        return sorted(stamps.values(), key=lambda stamp: stamp.name)

    def add_stamp(self, name: str, text: str, color: str = DEFAULT_STAMP_COLOR) -> None:
        if not name:
            raise ValueError("Informe um nome para o carimbo.")
        if not text:
            raise ValueError("Informe o texto do carimbo.")
        stamps = {stamp.name: stamp for stamp in self.list_stamps()}
        stamps[name] = StampDefinition(name=name, text=text, color=color)
        self._write(list(stamps.values()))

    def remove_stamp(self, name: str) -> None:
        self._write([stamp for stamp in self.list_stamps() if stamp.name != name])

    def _write(self, stamps: list[StampDefinition]) -> None:
        self._settings.remove(_LEGACY_GROUP)
        self._settings.remove(_ARRAY)
        self._settings.beginWriteArray(_ARRAY, len(stamps))
        try:
            for index, stamp in enumerate(sorted(stamps, key=lambda s: s.name)):
                self._settings.setArrayIndex(index)
                self._settings.setValue("name", stamp.name)
                self._settings.setValue("text", stamp.text)
                self._settings.setValue("color", stamp.color)
        finally:
            self._settings.endArray()
        self._settings.sync()

    def _legacy_stamps(self) -> list[StampDefinition]:
        """Carimbos do formato antigo: um grupo por nome, com "/" virando subgrupos."""
        found: list[StampDefinition] = []

        def visit(path: list[str]) -> None:
            keys = self._settings.childKeys()
            if "text" in keys:
                found.append(
                    StampDefinition(
                        name="/".join(path),
                        text=str(self._settings.value("text", "")),
                        color=str(self._settings.value("color", DEFAULT_STAMP_COLOR)),
                    )
                )
            for group in self._settings.childGroups():
                self._settings.beginGroup(group)
                try:
                    visit([*path, group])
                finally:
                    self._settings.endGroup()

        self._settings.beginGroup(_LEGACY_GROUP)
        try:
            for group in self._settings.childGroups():
                self._settings.beginGroup(group)
                try:
                    visit([group])
                finally:
                    self._settings.endGroup()
        finally:
            self._settings.endGroup()
        return found
