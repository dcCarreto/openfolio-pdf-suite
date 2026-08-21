"""Biblioteca de carimbos customizados (nome + texto + cor), persistida localmente via
`QSettings` — a forma idiomática do Qt de guardar preferências entre execuções, sem
precisar inventar um formato de arquivo próprio para algo tão simples."""

from dataclasses import dataclass

from PySide6.QtCore import QSettings

_ORG = "OpenFolio"
_APP = "OpenFolioPDFSuite"
_SETTINGS_GROUP = "custom_stamps"
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
        self._settings.beginGroup(_SETTINGS_GROUP)
        try:
            names = self._settings.childGroups()
            stamps = []
            for name in names:
                self._settings.beginGroup(name)
                try:
                    text = str(self._settings.value("text", ""))
                    color = str(self._settings.value("color", DEFAULT_STAMP_COLOR))
                    stamps.append(StampDefinition(name=name, text=text, color=color))
                finally:
                    self._settings.endGroup()
            return sorted(stamps, key=lambda stamp: stamp.name)
        finally:
            self._settings.endGroup()

    def add_stamp(self, name: str, text: str, color: str = DEFAULT_STAMP_COLOR) -> None:
        if not name:
            raise ValueError("Informe um nome para o carimbo.")
        if not text:
            raise ValueError("Informe o texto do carimbo.")

        self._settings.beginGroup(_SETTINGS_GROUP)
        try:
            self._settings.beginGroup(name)
            try:
                self._settings.setValue("text", text)
                self._settings.setValue("color", color)
            finally:
                self._settings.endGroup()
        finally:
            self._settings.endGroup()
        self._settings.sync()

    def remove_stamp(self, name: str) -> None:
        self._settings.beginGroup(_SETTINGS_GROUP)
        try:
            self._settings.remove(name)
        finally:
            self._settings.endGroup()
        self._settings.sync()
