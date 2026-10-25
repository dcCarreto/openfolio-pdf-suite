"""Atualizações (A17): escolhe, na lista de releases do GitHub, a atualização mais nova que a
que está instalada. A consulta e o download ficam na interface (`MainWindow.check_for_updates`),
que só consulta quando o usuário pede ou liga a verificação ao iniciar, e só baixa e instala
depois que ele vê o que mudou e aceita.

O usuário não vê número de versão: cada atualização é identificada, por dentro, pela data em
que foi publicada (`2026.10.21`, a versão do pyproject.toml; a tag é `v2026.10.21`). O texto do
que mudou vem do CHANGELOG.md, que o workflow de release põe nas notas da release.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# Só a lista pública de releases: nenhum dado do usuário ou dos documentos vai junto.
RELEASES_URL = "https://api.github.com/repos/dcCarreto/openfolio-pdf-suite/releases?per_page=20"
RELEASES_PAGE = "https://github.com/dcCarreto/openfolio-pdf-suite/releases"
# O instalador do Windows de cada release; o app só baixa arquivos do próprio repositório.
INSTALLER_NAME = "OpenFolioPDFSuite-Setup.exe"
DOWNLOAD_PREFIX = RELEASES_PAGE + "/download/"

_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)")
_SHA256 = re.compile(r"sha256:([0-9a-f]{64})")


def version_key(text: str) -> tuple | None:
    """Chave para comparar identificadores como "2026.10.21" e "v2026.10.21.1", ou None se o
    texto não for um."""
    match = _VERSION.fullmatch(text.strip())
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    return numbers + (0,) * (4 - len(numbers))


@dataclass
class Update:
    page: str  # página da release no GitHub
    notes: str  # o que mudou (Markdown, do CHANGELOG.md)
    installer_url: str | None = None  # instalador do Windows, quando a release traz um com hash
    installer_sha256: str | None = None
    installer_size: int = 0
    version: str = ""  # a tag da release ("v2026.10.22"): a data da edição


def newest_update(releases, current: str) -> Update | None:
    """A release publicada mais nova que `current`, ou None. `releases` é o JSON da API do
    GitHub; rascunhos e pré-releases (builds de teste) ficam de fora."""
    current_key = version_key(current)
    if current_key is None or not isinstance(releases, list):
        return None
    best = None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        key = version_key(str(release.get("tag_name") or ""))
        if key is not None and key > current_key and (best is None or key > best[0]):
            best = key, release
    return _update(best[1]) if best else None


def _update(release: dict) -> Update:
    url = str(release.get("html_url") or "")
    # O app só abre páginas do próprio repositório, venha o que vier na resposta.
    update = Update(
        page=url if url.startswith(RELEASES_PAGE + "/") else RELEASES_PAGE,
        notes=str(release.get("body") or ""),
        version=str(release.get("tag_name") or ""),
    )
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("name") != INSTALLER_NAME:
            continue
        download = str(asset.get("browser_download_url") or "")
        digest = _SHA256.fullmatch(str(asset.get("digest") or ""))
        size = asset.get("size")
        # Sem o hash publicado pelo GitHub não há como conferir o arquivo: fica só a página.
        if download.startswith(DOWNLOAD_PREFIX) and digest and isinstance(size, int) and size > 0:
            update.installer_url, update.installer_sha256, update.installer_size = download, digest.group(1), size
    return update


def installer_is_intact(path: Path, update: Update) -> bool:
    """Se o arquivo baixado é o instalador publicado: o tamanho e o SHA-256 que o GitHub
    informa para ele."""
    if not path.is_file() or path.stat().st_size != update.installer_size:
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == update.installer_sha256
