"""Versão do app: a do pyproject.toml, lida dos metadados do pacote instalado (`pip install -e .`
ou o app empacotado, que leva os metadados junto; ver packaging/pyinstaller)."""

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "openfolio-pdf-suite"

try:
    APP_VERSION = version(DISTRIBUTION)
except PackageNotFoundError:  # código-fonte sem `pip install -e .`
    APP_VERSION = "0.0.0+dev"
