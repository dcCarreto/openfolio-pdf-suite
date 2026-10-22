"""packaging/pyinstaller/third_party.py: licenças e código-fonte das bibliotecas que o app
leva de fora do Python, a partir do banco do gerenciador de pacotes."""

import importlib.util
import json
import platform
import sys
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Carregado pelo caminho: "packaging" também é o nome de um pacote do pip.
_spec = importlib.util.spec_from_file_location("third_party", ROOT / "packaging" / "pyinstaller" / "third_party.py")
third_party = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(third_party)


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _msys2_package(root, name, version, base, license, files):
    entry = root / "var/lib/pacman/local" / f"{name}-{version}"
    _write(entry / "desc", f"%NAME%\n{name}\n\n%VERSION%\n{version}\n\n%BASE%\n{base}\n\n%LICENSE%\n{license}\n\n")
    _write(entry / "files", "%FILES%\nucrt64/\n" + "".join(f"{f}\n" for f in files) + "\n")
    for f in files:
        _write(root / f, "texto da licença GPL" if "/licenses/" in f else "")


@pytest.fixture(autouse=True)
def _fresh_indexes():
    for cached in (third_party._msys2_index, third_party._dpkg_index, third_party._dpkg_status):
        cached.cache_clear()


def test_msys2_packages_give_the_license_texts_and_the_gpl_sources(tmp_path, monkeypatch):
    msys = tmp_path / "msys64"
    _msys2_package(msys, "mingw-w64-ucrt-x86_64-jbigkit", "2.1-5", "mingw-w64-jbigkit", "spdx:GPL-2.0-or-later",
                   ["ucrt64/bin/libjbig-0.dll", "ucrt64/share/licenses/jbigkit/COPYING"])
    _msys2_package(msys, "mingw-w64-ucrt-x86_64-gcc-libs", "15.2.0-8", "mingw-w64-gcc",
                   "spdx:GPL-3.0-or-later WITH GCC-exception-3.1", ["ucrt64/bin/libstdc++-6.dll"])
    _msys2_package(msys, "mingw-w64-ucrt-x86_64-libpng", "1.6.50-1", "mingw-w64-libpng", "spdx:libpng-2.0",
                   ["ucrt64/bin/libpng16-16.dll"])
    stray = _write(tmp_path / "outro" / "estranha.dll")
    python_owned = Path(sys.prefix) / "python3.dll"  # pacote Python: licença nos metadados
    monkeypatch.setattr(sys, "platform", "win32")

    out = tmp_path / "third-party"
    binaries = [msys / "ucrt64/bin/libjbig-0.dll", msys / "ucrt64/bin/libstdc++-6.dll",
                msys / "ucrt64/bin/libpng16-16.dll", stray, python_owned]
    unknown = third_party.collect([str(b) for b in binaries], out)

    assert unknown == [str(stray)]
    rows = json.loads((out / "components.json").read_text(encoding="utf-8"))
    assert [row for row in rows if row[0] not in ("Python", "Qt")] == [
        ["gcc-libs", "15.2.0-8", "GPL-3.0-or-later WITH GCC-exception-3.1"],
        ["jbigkit", "2.1-5", "GPL-2.0-or-later"],
        ["libpng", "1.6.50-1", "libpng-2.0"],
    ]
    # Só a GPL sem a exceção de runtime pede o fonte; e com "\n" até no Windows (o bash lê).
    assert (out / "sources.txt").read_bytes() == b"https://repo.msys2.org/mingw/sources/mingw-w64-jbigkit-2.1-5.src.tar.zst\n"
    assert "texto da licença GPL" in (out / "jbigkit.txt").read_text(encoding="utf-8")


def test_dpkg_packages_use_the_copyright_file_and_the_source_package(tmp_path, monkeypatch):
    library = _write(tmp_path / "usr/lib/libjbig.so.0")
    dpkg = tmp_path / "dpkg"
    _write(dpkg / "info" / "libjbig0.list", f"/.\n{library}\n")  # no Debian, libjbig0:amd64.list
    _write(dpkg / "status", "Package: libjbig0\nStatus: install ok installed\nSource: jbigkit (2.1-6.1)\n"
                            "Version: 2.1-6.1build1\nDescription: JBIGkit\n continua aqui\n\n"
                            "Package: zlib1g\nVersion: 1:1.3\n")
    doc = tmp_path / "doc"
    _write(doc / "libjbig0" / "copyright", "Files: *\nLicense: GPL-2+\n\nFiles: debian/*\nLicense: GPL-2+\n")
    monkeypatch.setattr(third_party, "DPKG_DIR", dpkg)
    monkeypatch.setattr(third_party, "DOC_DIR", doc)
    monkeypatch.setattr(sys, "platform", "linux")

    out = tmp_path / "third-party"
    assert third_party.collect([str(library)], out) == []

    assert ["libjbig0", "2.1-6.1build1", "GPL-2+"] in json.loads((out / "components.json").read_text(encoding="utf-8"))
    assert (out / "sources.txt").read_text(encoding="utf-8") == "jbigkit=2.1-6.1\n"


def test_python_and_qt_get_their_license_texts_and_qt_where_its_source_is(tmp_path):
    out = tmp_path / "third-party"
    assert third_party.collect([], out) == []

    rows = json.loads((out / "components.json").read_text(encoding="utf-8"))
    qt_version = ".".join(metadata.version("PySide6").split(".")[:3])
    assert rows == [["Python", platform.python_version(), "PSF-2.0"], ["Qt", qt_version, "LGPL-3.0-only"]]
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in (out / "Python.txt").read_text(encoding="utf-8")
    qt = (out / "Qt.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in qt and "GNU GENERAL PUBLIC LICENSE" in qt
    assert f"/PySide6-{qt_version}-src/" in qt and f"/{qt_version}/single/" in qt
    # Nenhum dos dois vai para o .tar: o texto da PSF fala em "GPL-compatible", e o fonte do Qt
    # (grande demais) fica indicado no texto.
    assert (out / "sources.txt").read_text(encoding="utf-8") == ""


@pytest.mark.parametrize(
    "license, needed",
    [
        ("GPL-2.0-or-later", True),
        ("LGPL-2.1-or-later", True),
        ("GPL-3.0-or-later WITH GCC-exception-3.1", False),
        ("GCC RUNTIME LIBRARY EXCEPTION ... GNU General Public License", False),
        ("Apache-2.0", False),
    ],
)
def test_only_gpl_and_lgpl_need_the_source(license, needed):
    assert third_party.needs_source(license) is needed
