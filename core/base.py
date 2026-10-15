"""Classes e helpers base compartilhados pelos módulos de core."""

import contextlib
import os
import shutil
import tempfile
from collections.abc import Iterator

from pypdf import PdfReader


class PDFOperation:
    """Interface base para operações sobre arquivos PDF."""

    def run(self, *args, **kwargs):
        raise NotImplementedError


class EncryptedPDFError(ValueError):
    """Levantado ao tentar processar como entrada um PDF protegido por senha."""


def open_reader(input_path: str) -> PdfReader:
    """Abre um PdfReader recusando PDFs protegidos por senha com uma mensagem clara.

    Sem essa checagem, cada operação derrubaria mais tarde — ao acessar `.pages` — com um
    FileNotDecryptedError cru do pypdf. Ferramentas que lidam com PDFs protegidos de
    propósito (Proteger/Remover senha) não usam este helper; leem o PdfReader diretamente.
    """
    reader = PdfReader(input_path)
    if reader.is_encrypted:
        raise EncryptedPDFError(
            'Este PDF está protegido por senha. Use a ferramenta "Remover senha" antes de '
            "processá-lo aqui."
        )
    return reader


@contextlib.contextmanager
def atomic_output(output_path: str) -> Iterator[str]:
    """Entrega um caminho temporário na mesma pasta do destino e só o põe no lugar do
    destino se o bloco terminar sem erro.

    Assim, uma operação que falha no meio (ou uma verificação que reprova o resultado,
    como a da redação) nunca deixa um arquivo pela metade — nem destrói o original quando
    o destino é o próprio arquivo de entrada.

    No Windows, `os.replace` falha com acesso negado se o destino estiver aberto por outro
    handle sem compartilhamento de exclusão — caso do PDF aberto no visualizador (o pdfium
    mantém o arquivo aberto). Nesse caso o conteúdo, já pronto e verificado, é copiado por
    cima do destino.
    """
    directory = os.path.dirname(os.path.abspath(output_path))
    fd, temp_path = tempfile.mkstemp(prefix=".openfolio-", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        yield temp_path
        try:
            os.replace(temp_path, output_path)
        except PermissionError:
            shutil.copyfile(temp_path, output_path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(temp_path)


def require_valid_page_index(total_pages: int, index: int, *, label: str = "Página") -> None:
    """Levanta um ValueError claro se `index` não for um índice de página válido."""
    if not 0 <= index < total_pages:
        raise ValueError(
            f"{label} inválida: índice {index} (o documento tem {total_pages} "
            f"página(s), de 0 a {total_pages - 1})."
        )
