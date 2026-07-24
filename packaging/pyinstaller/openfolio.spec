# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o OpenFolio PDF Suite.

Gera um build "onedir" (uma pasta com o executável e todas as dependências), o mesmo
formato que os empacotadores de cada plataforma esperam como entrada:
- Windows: packaging/windows/installer.iss (Inno Setup)
- Linux:   packaging/linux/build_appimage.sh e build_deb.sh
- macOS:   packaging/macos/build_dmg.sh

Rodar a partir da raiz do projeto:
    pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve().parent.parent
ICONS_DIR = PROJECT_ROOT / "packaging" / "icons"

APP_NAME = "OpenFolioPDFSuite"

if sys.platform == "win32":
    app_icon = str(ICONS_DIR / "icon.ico")
elif sys.platform == "darwin":
    app_icon = str(ICONS_DIR / "icon.icns")
else:
    app_icon = None

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "assets" / "icon.png"), "assets"),
        (str(PROJECT_ROOT / "assets" / "logo.svg"), "assets"),
    ],
    hiddenimports=[
        "pyhanko_certvalidator",
        "asn1crypto",
        "oscrypto",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
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
        },
    )
