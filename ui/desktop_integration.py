"""O AppImage no menu de aplicativos do Linux.

O AppImage roda sem instalar, e por isso não aparecia no menu nem na escolha do programa para
abrir PDF (o `.deb` aparece). Com o consentimento do usuário (ver `MainWindow`), o app grava
em `~/.local/share` um `.desktop` que aponta para o arquivo do AppImage, e o reescreve se o
arquivo mudar de lugar. O `TryExec` esconde a entrada se o AppImage for apagado.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Outro nome que o do .deb (packaging/linux/openfolio-pdf-suite.desktop): os dois convivem.
DESKTOP_ID = "openfolio-pdf-suite-appimage"


def appimage_path() -> str | None:
    """O arquivo do AppImage em execução (o runtime do AppImage põe em $APPIMAGE)."""
    path = os.environ.get("APPIMAGE")
    return path if sys.platform.startswith("linux") and path else None


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def desktop_file() -> Path:
    return _data_home() / "applications" / f"{DESKTOP_ID}.desktop"


def icon_file() -> Path:
    return _data_home() / "icons" / "hicolor" / "256x256" / "apps" / f"{DESKTOP_ID}.png"


def exec_argument(path: str) -> str:
    """`path` como argumento do Exec (especificação Desktop Entry): entre aspas, com `"`,
    `` ` ``, `$` e `\\` escapados, depois a barra dobrada de novo (escape de string) e o `%`
    dobrado."""
    quoted = "".join("\\" + c if c in '"`$\\' else c for c in path)
    return '"' + quoted.replace("\\", "\\\\").replace("%", "%%") + '"'


def _desktop_entry(appimage: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=OpenFolio PDF Suite\n"
        "GenericName=Editor de PDF\n"
        "Comment=Suite completa e open source de manipulação de PDF, 100% local\n"
        f"TryExec={appimage.replace(chr(92), chr(92) * 2)}\n"
        f"Exec={exec_argument(appimage)} %F\n"
        "MimeType=application/pdf;\n"
        f"Icon={icon_file()}\n"
        "Categories=Office;\n"
        "Terminal=false\n"
        "StartupWMClass=OpenFolioPDFSuite\n"
    )


def is_integrated() -> bool:
    return desktop_file().is_file()


def integrate(appimage: str) -> None:
    """Grava (ou reescreve) o `.desktop` e o ícone."""
    icon_source = Path(os.environ.get("APPDIR", "")) / "openfolio-pdf-suite.png"
    if icon_source.is_file():  # o AppDir só existe enquanto o AppImage roda: o ícone é copiado
        icon_file().parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_source, icon_file())
    desktop_file().parent.mkdir(parents=True, exist_ok=True)
    desktop_file().write_text(_desktop_entry(appimage), encoding="utf-8")
    _refresh_menu()


def remove() -> None:
    desktop_file().unlink(missing_ok=True)
    icon_file().unlink(missing_ok=True)
    _refresh_menu()


def follow(appimage: str) -> None:
    """Se a entrada existe e aponta para outro arquivo (o AppImage foi movido), aponta-a para
    este."""
    if is_integrated() and desktop_file().read_text(encoding="utf-8") != _desktop_entry(appimage):
        integrate(appimage)


def _refresh_menu() -> None:
    # A maioria dos ambientes vê a mudança sozinha; o cache de tipos, quando a distribuição usa,
    # é atualizado por este programa dela (sem ele, não há o que atualizar).
    tool = shutil.which("update-desktop-database")
    if tool:
        subprocess.run([tool, str(desktop_file().parent)], check=False, capture_output=True, timeout=30)
