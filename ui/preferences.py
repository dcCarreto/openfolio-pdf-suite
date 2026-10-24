"""Preferências do usuário guardadas entre sessões: arquivos recentes, última pasta, idioma,
tema, verificação de atualização, atalhos de teclado e a assinatura e as iniciais do "Preencher e assinar".

Ficam no mesmo QSettings da geometria da janela. Sem QSettings (testes), as preferências
vivem só na memória do processo.
"""

import os
import time
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

    # -- tema (A14) ---------------------------------------------------------------

    def theme(self) -> str:
        """"dark" (padrão), "light" ou "system" (ver `ui/theme.py`)."""
        value = str(self._get("ui/theme", "dark") or "dark")
        return value if value in ("dark", "light", "system") else "dark"

    def set_theme(self, theme: str) -> None:
        self._set("ui/theme", theme)

    # -- visualizador ---------------------------------------------------------------

    def page_layout(self) -> str | None:
        """O modo de exibição que o usuário escolheu por último (ver `ui/viewer/pdf_viewer.py`)."""
        value = self._get("viewer/layout")
        return None if value is None else str(value)

    def set_page_layout(self, layout: str) -> None:
        self._set("viewer/layout", layout)

    # -- verificação de atualização (A17) -----------------------------------------

    def check_updates_on_start(self) -> bool:
        """Desligado até o usuário ligar: o app não acessa a rede por conta própria."""
        return str(self._get("updates/check_on_start", "false")).lower() == "true"

    def set_check_updates_on_start(self, enabled: bool) -> None:
        self._set("updates/check_on_start", "true" if enabled else "false")

    def update_check_due(self, now: float | None = None) -> bool:
        """Se a verificação ao iniciar deve consultar o GitHub: no máximo uma vez por dia (a
        API aceita 60 consultas por hora por IP, e uma atualização não sai a cada abertura)."""
        try:
            last = float(self._get("updates/last_check"))
        except (TypeError, ValueError):
            return True
        elapsed = (time.time() if now is None else now) - last
        return not 0 <= elapsed < 24 * 60 * 60  # relógio voltou atrás: consulta

    def set_last_update_check(self, when: float | None = None) -> None:
        self._set("updates/last_check", str(time.time() if when is None else when))

    # -- anotações (M27) ----------------------------------------------------------

    def annotation_author(self) -> str | None:
        """O autor das anotações novas, ou None se ainda não foi escolhido (usa o do sistema)."""
        value = self._get("annotations/author")
        return None if value is None else str(value)

    def set_annotation_author(self, author: str) -> None:
        self._set("annotations/author", author)

    # -- menu de aplicativos do Linux (AppImage) -----------------------------------

    def app_menu_offered(self) -> bool:
        """Se o AppImage já perguntou se deve aparecer no menu de aplicativos (pergunta uma vez)."""
        return str(self._get("linux/app_menu_offered", "false")).lower() == "true"

    def set_app_menu_offered(self, offered: bool) -> None:
        self._set("linux/app_menu_offered", "true" if offered else "false")

    # -- atalhos de teclado (A18) -------------------------------------------------

    def shortcut(self, command: str) -> str | None:
        """Atalho escolhido para `command` ("" = nenhum), ou None se ficou o de fábrica."""
        value = self._get(f"shortcuts/{command}")
        return None if value is None else str(value)

    def set_shortcut(self, command: str, keys: str | None) -> None:
        key = f"shortcuts/{command}"
        if keys is not None:
            self._set(key, keys)
        elif self._settings is None:
            self._memory.pop(key, None)
        else:
            self._settings.remove(key)

    # -- assinatura e iniciais (A04) ----------------------------------------------

    def saved_image(self, kind: str) -> bytes:
        """PNG/JPEG guardado para `kind` ("signature" ou "initials"), ou b"" se não houver."""
        value = self._get(f"fill_sign/{kind}")
        return bytes(value) if value else b""

    def set_saved_image(self, kind: str, data: bytes) -> None:
        self._set(f"fill_sign/{kind}", data)


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
