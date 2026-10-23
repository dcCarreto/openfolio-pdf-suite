"""Baixa os idiomas do Tesseract que os instaladores levam junto com o app.

Rodar a partir da raiz do projeto, antes do PyInstaller:
    python packaging/fetch_tessdata.py

Grava em build/tessdata/ e confere o SHA-256 de cada arquivo (um arquivo trocado no caminho
não entra no instalador). Inglês e português são os modelos "fast" (os mesmos do instalador
oficial do Tesseract para Windows); "osd" detecta a orientação de páginas escaneadas de lado.
Os dados são do projeto tesseract-ocr, licença Apache 2.0.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

_BASE = "https://raw.githubusercontent.com/tesseract-ocr"
LANGUAGES = {
    "eng": (f"{_BASE}/tessdata_fast/4.1.0/eng.traineddata", "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"),
    "por": (f"{_BASE}/tessdata_fast/4.1.0/por.traineddata", "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"),
    "osd": (f"{_BASE}/tessdata/4.1.0/osd.traineddata", "e19f2ae860792fdf372cf48d8ce70ae5da3c4052962fe22e9de1f680c374bb0e"),
}
TESSDATA_DIR = Path(__file__).resolve().parent.parent / "build" / "tessdata"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    for code, (url, expected) in LANGUAGES.items():
        target = TESSDATA_DIR / f"{code}.traineddata"
        if target.is_file() and _sha256(target) == expected:
            print(f"{code}: já baixado")
            continue
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as response:
            partial.write_bytes(response.read())
        if _sha256(partial) != expected:
            partial.unlink()
            print(f"{code}: SHA-256 não confere ({url})", file=sys.stderr)
            return 1
        partial.replace(target)
        print(f"{code}: baixado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
