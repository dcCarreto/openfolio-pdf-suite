# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o OpenFolio PDF Suite.

Gera um build "onedir" (uma pasta com o executável do app, o da linha de comando `openfolio`
e todas as dependências), o mesmo formato que os empacotadores de cada plataforma esperam
como entrada:
- Windows: packaging/windows/installer.iss (Inno Setup)
- Linux:   packaging/linux/build_appimage.sh e build_deb.sh
- macOS:   packaging/macos/build_dmg.sh

Rodar a partir da raiz do projeto, com o Tesseract instalado na máquina de build pelo
gerenciador de pacotes (MSYS2 no Windows, apt no Linux, Homebrew no macOS), que diz a
licença e o código-fonte de cada biblioteca que vai junto:
    python packaging/fetch_tessdata.py
    pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

PROJECT_ROOT = Path(SPECPATH).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, SPECPATH)
import third_party  # noqa: E402

ICONS_DIR = PROJECT_ROOT / "packaging" / "icons"
THIRD_PARTY_DIR = PROJECT_ROOT / "build" / "third-party"

APP_NAME = "OpenFolioPDFSuite"

# O Tesseract vai dentro do app (o usuário não instala nada para o OCR). O binário entra em
# `binaries`, então o PyInstaller leva junto as bibliotecas de que ele precisa (DLLs,
# .so, .dylib), na mesma pasta; os idiomas vêm de packaging/fetch_tessdata.py. O app o
# encontra em sys._MEIPASS (core/ocr.py, `find_tesseract`).
from core.ocr import find_tesseract  # noqa: E402

TESSERACT = find_tesseract()
TESSDATA_DIR = PROJECT_ROOT / "build" / "tessdata"
if not TESSERACT:
    raise SystemExit("Tesseract não encontrado: instale-o na máquina de build (o app leva uma cópia dele).")
if not all((TESSDATA_DIR / f"{code}.traineddata").is_file() for code in ("eng", "por", "osd")):
    raise SystemExit("Idiomas do Tesseract ausentes: rode antes  python packaging/fetch_tessdata.py")

if sys.platform == "win32":
    app_icon = str(ICONS_DIR / "icon.ico")
elif sys.platform == "darwin":
    app_icon = str(ICONS_DIR / "icon.icns")
else:
    app_icon = None

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[(TESSERACT, ".")],
    datas=[
        (str(TESSDATA_DIR), "tessdata"),
        (str(PROJECT_ROOT / "assets" / "icon.png"), "assets"),
        (str(PROJECT_ROOT / "assets" / "logo.svg"), "assets"),
        # Fontes embutidas no texto que o app desenha nos PDFs (core/fonts.py) e o perfil
        # de cor sRGB dos arquivos PDF/A (core/pdfa.py).
        (str(PROJECT_ROOT / "core" / "data" / "fonts"), "core/data/fonts"),
        (str(PROJECT_ROOT / "core" / "data" / "icc"), "core/data/icc"),
        # Metadados do app (a versão vem deles, core/version.py) e de cada dependência, que
        # trazem os textos das licenças listadas em Ajuda > Sobre (ui/about_dialog.py).
        *copy_metadata("openfolio-pdf-suite", recursive=True),
    ],
    hiddenimports=[
        "pyhanko_certvalidator",
        "asn1crypto",
        "oscrypto",
        # As abas são importadas pelo nome só quando abertas (ui/main_window.py), então a
        # análise estática não as encontra sozinha.
        *collect_submodules("ui.pages"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# O comando `openfolio` (core/cli.py): um executável de console na mesma pasta, que usa as
# mesmas bibliotecas, o Tesseract e os dados do app.
cli = Analysis(
    [str(PROJECT_ROOT / "packaging" / "pyinstaller" / "openfolio_cli.py")],
    pathex=[str(PROJECT_ROOT)],
    hiddenimports=["pyhanko_certvalidator", "asn1crypto", "oscrypto"],
    noarchive=False,
)

# Licenças e código-fonte das bibliotecas de fora do Python (packaging/pyinstaller/third_party.py).
# Uma biblioteca sem pacote de origem não tem licença conhecida: a release não sai com ela.
unknown = third_party.collect([source for _dest, source, _kind in a.binaries + cli.binaries], THIRD_PARTY_DIR)
if unknown:
    message = "Bibliotecas sem pacote de origem (licença desconhecida): " + ", ".join(unknown)
    if os.environ.get("CI"):
        raise SystemExit(message)
    print("AVISO:", message)
a.datas += [(f"third-party/{f.name}", str(f), "DATA") for f in THIRD_PARTY_DIR.iterdir()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=app_icon,
)

cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="openfolio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=app_icon,
)

coll = COLLECT(
    exe,
    cli_exe,
    a.binaries,
    a.datas,
    cli.binaries,
    cli.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=app_icon,
        bundle_identifier="com.dccarreto.openfoliopdfsuite",
        info_plist={
            "CFBundleName": "OpenFolio PDF Suite",
            "CFBundleDisplayName": "OpenFolio PDF Suite",
            "NSHighResolutionCapable": True,
            # Aparece em "Abrir com" para PDFs; o arquivo chega pelo evento FileOpen do Qt
            # (ver ui/app_events.py).
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "PDF",
                    "CFBundleTypeRole": "Editor",
                    "LSHandlerRank": "Alternate",
                    "LSItemContentTypes": ["com.adobe.pdf"],
                }
            ],
        },
    )
