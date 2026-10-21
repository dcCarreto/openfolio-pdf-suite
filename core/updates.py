"""Verificação de atualização (A17): escolhe, na lista de releases do GitHub, a mais nova que
a versão em uso. A consulta em si fica na interface (`MainWindow.check_for_updates`), que só
a faz quando o usuário pede ou liga a verificação ao iniciar.
"""

import re

# Só a lista pública de releases: nenhum dado do usuário ou dos documentos vai junto.
RELEASES_URL = "https://api.github.com/repos/dcCarreto/openfolio-pdf-suite/releases?per_page=20"
RELEASES_PAGE = "https://github.com/dcCarreto/openfolio-pdf-suite/releases"

_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?")


def version_key(text: str) -> tuple | None:
    """Chave para comparar versões como "0.2.0" e "v0.2.0-beta.1" (a final vem depois das
    pré-versões dela), ou None se o texto não for uma versão."""
    match = _VERSION.fullmatch(text.strip())
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    numbers += (0,) * (3 - len(numbers))
    if match.group(2) is None:
        return numbers, 1, ()
    pre = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in match.group(2).split("."))
    return numbers, 0, pre


def is_prerelease(version: str) -> bool:
    key = version_key(version)
    return key is not None and key[1] == 0


def newest_release(releases, current: str) -> tuple[str, str] | None:
    """(versão, página da release) da release publicada mais nova que `current`, ou None.

    `releases` é o JSON da API do GitHub. Rascunhos ficam de fora; pré-versões (beta, rc)
    só contam para quem já usa uma.
    """
    current_key = version_key(current)
    if current_key is None or not isinstance(releases, list):
        return None
    accept_prerelease = current_key[1] == 0
    best = None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "")
        key = version_key(tag)
        if key is None or (key[1] == 0 or release.get("prerelease")) and not accept_prerelease:
            continue
        if key > current_key and (best is None or key > best[0]):
            url = str(release.get("html_url") or "")
            # O app só abre páginas do próprio repositório, venha o que vier na resposta.
            best = key, tag.lstrip("v"), url if url.startswith(RELEASES_PAGE + "/") else RELEASES_PAGE
    return (best[1], best[2]) if best else None
