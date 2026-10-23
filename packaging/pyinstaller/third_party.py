"""Licenças e código-fonte das bibliotecas que o app leva de fora do Python: o Tesseract com
as dependências dele e, no Linux, as bibliotecas do sistema de que o Qt precisa. Também as do
próprio Python e do Qt, cujos textos de licença os pacotes Python não trazem.

Quem diz de que pacote veio cada biblioteca é o gerenciador de pacotes da máquina de build
(MSYS2 no Windows, dpkg no Linux, Homebrew no macOS), com a licença, os textos dela e o
código-fonte daquela versão. O spec do PyInstaller chama `collect` com os binários do app,
que grava em build/third-party/ (e o app leva a pasta):
- um .txt por pacote com os textos das licenças (Ajuda > Sobre abre a pasta);
- components.json, as linhas da tabela do Sobre;
- sources.txt, o código-fonte dos pacotes GPL e LGPL, que packaging/fetch_sources.sh baixa e
  o workflow anexa à release: a GPL pede oferecer o fonte, e oferecê-lo no mesmo lugar do
  binário cumpre isso.
"""

import functools
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

LICENSES_DIR = Path(__file__).resolve().parent.parent / "licenses"  # textos da GPL 3 e da LGPL 3
DPKG_DIR = Path("/var/lib/dpkg")
DOC_DIR = Path("/usr/share/doc")
MSYS2_SOURCES = "https://repo.msys2.org/mingw/sources/"
# Os pacotes Python levam as licenças nos próprios metadados (ui/about_dialog.py); o
# sys.path inclui a pasta das extensões do próprio Python (DLLs, no Windows).
_PYTHON_DIRS = {
    Path(p).resolve()
    for p in (*sys.path, sys.prefix, sys.base_prefix, Path(getattr(sys, "_base_executable", sys.executable)).parent)
    if p
}
_LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)", re.IGNORECASE)


@dataclass
class Package:
    name: str
    version: str
    license: str
    license_files: list[Path]
    source: str  # o que packaging/fetch_sources.sh baixa: uma URL ou, no Linux, pacote=versão
    notice: str = ""  # vai no texto, antes das licenças


def needs_source(text: str) -> bool:
    """GPL e LGPL pedem oferecer o código-fonte; a exceção de runtime do GCC (libgcc,
    libstdc++) dispensa."""
    return "GPL" in text and "GCC-exception" not in text and "RUNTIME LIBRARY EXCEPTION" not in text.upper()


def _pacman_fields(path: Path) -> dict[str, list[str]]:
    """Os campos de um arquivo do banco local do pacman (`%NOME%` seguido dos valores)."""
    fields: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.fullmatch(r"%[A-Z0-9]+%", line):
            current = fields.setdefault(line.strip("%"), [])
        elif line and current is not None:
            current.append(line)
    return fields


@functools.cache
def _msys2_index(root: Path) -> dict[Path, Path]:
    """Cada arquivo instalado no MSYS2 -> a pasta do pacote dele no banco do pacman."""
    index = {}
    for entry in (root / "var/lib/pacman/local").iterdir():
        if (entry / "files").is_file():
            for name in _pacman_fields(entry / "files").get("FILES", []):
                index[(root / name).resolve()] = entry
    return index


def _msys2_owner(path: Path) -> Package | None:
    root = next((p for p in path.parents if (p / "var/lib/pacman/local").is_dir()), None)
    entry = _msys2_index(root).get(path) if root else None
    if entry is None:
        return None
    desc = _pacman_fields(entry / "desc")
    files = _pacman_fields(entry / "files")["FILES"]
    version = desc["VERSION"][0]
    return Package(
        name=re.sub(r"^mingw-w64-(?:[a-z]+-)?(?:x86_64|aarch64|i686)-", "", desc["NAME"][0]),
        version=version,
        license=" AND ".join(item.removeprefix("spdx:") for item in desc.get("LICENSE", [])) or "?",
        license_files=[root / name for name in files if "/share/licenses/" in name and not name.endswith("/")],
        source=f"{MSYS2_SOURCES}{desc['BASE'][0]}-{version}.src.tar.zst",
    )


@functools.cache
def _dpkg_index() -> dict[Path, str]:
    """Cada biblioteca ou programa instalado pelo dpkg -> o nome do pacote (os caminhos
    resolvidos: com o /usr unificado, a lista diz /lib e o arquivo está em /usr/lib). O
    programa conta: o executável do Tesseract (/usr/bin/tesseract) vai junto no app."""
    index = {}
    for listing in (DPKG_DIR / "info").glob("*.list"):
        for line in listing.read_text(encoding="utf-8", errors="replace").splitlines():
            if ".so" in line or Path(line).parent.name == "bin":
                index[Path(line).resolve()] = listing.stem.split(":")[0]
    return index


@functools.cache
def _dpkg_status() -> dict[str, dict[str, str]]:
    status = {}
    for stanza in (DPKG_DIR / "status").read_text(encoding="utf-8", errors="replace").split("\n\n"):
        fields = dict(re.findall(r"^([A-Za-z-]+): *(.*)$", stanza, re.MULTILINE))
        if "Package" in fields:
            status[fields["Package"]] = fields
    return status


def _dpkg_owner(path: Path) -> Package | None:
    name = _dpkg_index().get(path)
    if name is None:
        return None
    fields = _dpkg_status()[name]
    copyright_file = DOC_DIR / name / "copyright"
    text = copyright_file.read_text(encoding="utf-8", errors="replace") if copyright_file.is_file() else ""
    # Source: "pacote" ou "pacote (versão)", quando a versão do fonte é outra.
    source = re.fullmatch(r"(\S+)(?: \((\S+)\))?", fields.get("Source", name))
    return Package(
        name=name,
        version=fields["Version"],
        license=", ".join(dict.fromkeys(re.findall(r"^License: *(\S.*)$", text, re.MULTILINE))) or "?",
        license_files=[copyright_file] if text else [],
        source=f"{source.group(1)}={source.group(2) or fields['Version']}",  # type: ignore[union-attr]
    )


@functools.cache
def _homebrew_info(formula: str) -> dict:
    output = subprocess.run(["brew", "info", "--json=v2", formula], capture_output=True, text=True, check=True).stdout
    return json.loads(output)["formulae"][0]


def _homebrew_owner(path: Path) -> Package | None:
    parts = path.parts
    if "Cellar" not in parts:
        return None
    at = parts.index("Cellar")
    formula, version = parts[at + 1], parts[at + 2]
    keg = Path(*parts[: at + 3])
    info = _homebrew_info(formula)
    license = info.get("license") or "?"
    return Package(
        name=formula,
        version=version,
        license=license if isinstance(license, str) else json.dumps(license),
        license_files=sorted(p for p in keg.iterdir() if p.is_file() and _LICENSE_FILE.match(p.name)),
        source=info["urls"]["stable"]["url"],
    )


def _python_package() -> Package | None:
    """O próprio Python: a licença PSF traz os avisos do que ele leva (OpenSSL, libffi...)."""
    executable_dir = Path(getattr(sys, "_base_executable", sys.executable)).parent
    # Na raiz da instalação no Windows; junto da biblioteca padrão no Linux e no macOS.
    folders = [Path(sys.base_prefix), executable_dir, Path(os.__file__).parent]
    found = next((f / "LICENSE.txt" for f in folders if (f / "LICENSE.txt").is_file()), None)
    if found is None:
        return None
    return Package("Python", platform.python_version(), "PSF-2.0", [found], source="")


def _qt_package() -> Package:
    """O Qt que vem no PySide6. Os wheels não trazem o texto da LGPL nem o código-fonte, que
    é grande demais para anexar: a GPL 3 (seção 6d) aceita indicar onde ele está."""
    version = ".".join(metadata.version("PySide6").split(".")[:3])
    minor = ".".join(version.split(".")[:2])
    notice = (
        "\nCódigo-fonte desta versão:\n"
        f"- Qt: https://download.qt.io/official_releases/qt/{minor}/{version}/single/\n"
        f"  (as versões antigas passam para https://download.qt.io/archive/qt/{minor}/{version}/single/)\n"
        f"- PySide6 e Shiboken6: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{version}-src/\n"
    )
    files = [LICENSES_DIR / "LGPL-3.0.txt", LICENSES_DIR / "GPL-3.0.txt"]
    return Package("Qt", version, "LGPL-3.0-only", files, source="", notice=notice)


def collect(binaries: list[str], out_dir: Path) -> list[str]:
    """Grava em `out_dir` as licenças e o código-fonte dos pacotes de onde vieram os
    `binaries`; devolve os que nenhum gerenciador de pacotes conhece (fora os dos pacotes
    Python)."""
    owner = {"win32": _msys2_owner, "darwin": _homebrew_owner}.get(sys.platform, _dpkg_owner)
    packages: dict[str, Package] = {}
    unknown = []
    for binary in binaries:
        path = Path(binary).resolve()
        package = owner(path)
        if package is not None:
            packages[package.name] = package
        elif not any(path.is_relative_to(d) for d in _PYTHON_DIRS):
            unknown.append(binary)
    packages["Qt"] = _qt_package()
    python = _python_package()
    if python is None:
        unknown.append("LICENSE.txt do Python")
    else:
        packages["Python"] = python

    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    rows, sources = [], []
    for package in sorted(packages.values(), key=lambda p: p.name.lower()):
        text = f"{package.name} {package.version}\nLicença: {package.license}\n{package.notice}" + "".join(
            f"\n===== {f.name} =====\n\n{f.read_text(encoding='utf-8', errors='replace')}" for f in package.license_files
        )
        (out_dir / f"{package.name}.txt").write_text(text, encoding="utf-8")
        rows.append([package.name, package.version, package.license])
        if package.source and needs_source(text):  # o texto da PSF fala em "GPL-compatible"
            sources.append(package.source)
    (out_dir / "components.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    # "\n" mesmo no Windows: o fetch_sources.sh lê com o bash.
    (out_dir / "sources.txt").write_text("".join(f"{s}\n" for s in dict.fromkeys(sources)), encoding="utf-8", newline="\n")
    return unknown
