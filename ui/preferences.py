"""Preferências do usuário guardadas entre sessões: arquivos recentes, última pasta e idioma.

Ficam no mesmo QSettings da geometria da janela. Sem QSettings (testes), as preferências
vivem só na memória do processo.
"""

import os
from pathlib import Path

_MAX_RECENT = 10


class Preferences:
    def __init__(self, settings=None):
        self._settings = settings
        self._memory: dict[str, object] = {}

    def _get(self, key: str, default=None):
        if self._settings is None:
            return self._memory.get(key, default)
        value = self._settings.value(key, default)
        return default if value is None else value

    def _set(self, key: str, value) -> None:
        if self._settings is None:
            self._memory[key] = value
        else:
            self._settings.setValue(key, value)

    # -- arquivos recentes --------------------------------------------------------

    def recent_files(self) -> list[str]:
        value = self._get("files/recent", [])
        if isinstance(value, str):
            value = [value]  # o QSettings devolve uma lista de um item como texto
        return [path for path in (value or []) if os.path.isfile(path)]

    def add_recent_file(self, path: str) -> None:
        path = os.path.abspath(path)
        recent = [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        self._set("files/recent", [path, *recent][:_MAX_RECENT])
        self.set_last_folder(str(Path(path).parent))

    def clear_recent_files(self) -> None:
        self._set("files/recent", [])

    # -- última pasta -------------------------------------------------------------

    def last_folder(self) -> str:
        folder = str(self._get("files/last_folder", "") or "")
        return folder if folder and os.path.isdir(folder) else ""

    def set_last_folder(self, folder: str) -> None:
        if folder:
            self._set("files/last_folder", folder)

    # -- idioma -------------------------------------------------------------------

    def language(self) -> str | None:
        value = self._get("ui/language")
        return str(value) if value else None

    def set_language(self, language: str) -> None:
        self._set("ui/language", language)


_current = Preferences()


def preferences() -> Preferences:
    return _current


def use_preferences(prefs: Preferences) -> None:
    """A janela principal instala as preferências ligadas ao QSettings do app."""
    global _current
    _current = prefs


def start_folder(path: str | None = None) -> str:
    """Pasta inicial para um diálogo de arquivo: a de `path`, se houver, senão a última
    usada."""
    if path:
        return path
    return preferences().last_folder()


def remember_folder_of(path: str) -> None:
    if path:
        target = Path(path)
        preferences().set_last_folder(str(target if target.is_dir() else target.parent))
