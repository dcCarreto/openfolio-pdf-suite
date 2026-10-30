"""Classes e helpers base compartilhados pelos módulos de core."""

import contextlib
import math
import os
import shutil
import tempfile
from collections.abc import Iterator

import pypdfium2 as pdfium
from pypdf import PasswordType, PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions

from .messages import Message, plural_message


class EncryptedPDFError(ValueError):
    """O PDF está protegido e não pode ser usado pela operação pedida."""


class RestrictedPDFError(EncryptedPDFError):
    """O PDF abre, mas a proteção ou as permissões dele não permitem a operação pedida."""


# Para que a operação precisa do PDF de entrada (ver `open_reader`).
READ = "read"  # só lê a estrutura ou renderiza, como um leitor de PDF
EXTRACT = "extract"  # copia conteúdo para fora do documento (texto, imagens)
MODIFY = "modify"  # gera um PDF novo a partir deste
PRINT = "print"  # imprime o documento

_LOCKED_MESSAGE = (
    "Este PDF está protegido por senha. Abra-o no visualizador (que pede a senha) para usá-lo "
    'nas ferramentas de leitura, ou use "Remover senha" em Proteger para trabalhar sobre uma '
    "cópia sem proteção."
)
_RESTRICTED_MODIFY_MESSAGE = (
    "Este PDF abre sem senha, mas o autor restringiu alterações com uma senha de permissões. "
    'Para alterá-lo, use "Remover senha" em Proteger informando a senha de permissões — o '
    "resultado sai sem proteção, e você pode protegê-lo de novo depois."
)
_PROTECTED_MODIFY_MESSAGE = (
    "Este PDF está protegido por senha. Alterá-lo aqui geraria uma cópia sem a proteção; use "
    '"Remover senha" em Proteger e, se quiser, proteja o resultado de novo depois.'
)
_EXTRACT_DENIED_MESSAGE = (
    "O autor deste PDF não permite copiar o conteúdo dele (texto e imagens). Para extrair, "
    'use "Remover senha" em Proteger informando a senha de permissões.'
)
_PRINT_DENIED_MESSAGE = (
    "O autor deste PDF não permite imprimi-lo. Para imprimir, use \"Remover senha\" em "
    "Proteger informando a senha de permissões."
)

_known_passwords: dict[str, str] = {}


def _password_key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def remember_password(path, password: str) -> None:
    """Guarda a senha que o usuário digitou ao abrir `path` no visualizador, para que as
    ferramentas de leitura não precisem pedi-la de novo. Fica só na memória do processo."""
    _known_passwords[_password_key(path)] = password


def forget_password(path) -> None:
    _known_passwords.pop(_password_key(path), None)


def known_password(path) -> str | None:
    return _known_passwords.get(_password_key(path))


def open_reader(input_path: str, *, purpose: str = MODIFY) -> PdfReader:
    """Abre um PdfReader tratando PDFs protegidos de acordo com o `purpose` da operação.

    PDF sem proteção: abre normalmente. PDF protegido:

    - Precisa ser decifrado: com a senha que o usuário digitou no visualizador (ver
      `remember_password`) ou sem senha nenhuma, caso de PDFs que só restringem permissões.
      Se não der, `EncryptedPDFError`.
    - `READ` (listar, verificar, renderizar) funciona sempre que o PDF abre.
    - `EXTRACT` respeita a permissão de cópia definida pelo autor, a menos que a senha
      conhecida seja a de proprietário. `PRINT` faz o mesmo com a permissão de impressão.
    - `MODIFY` é recusado com `RestrictedPDFError`: o pypdf gravaria a saída sem a
      proteção, e uma ferramenta de edição não deve remover proteção sem o usuário pedir.
      A mensagem aponta o caminho certo ("Remover senha" em Proteger).

    Sem essa checagem, cada operação derrubaria mais tarde — ao acessar `.pages` — com um
    FileNotDecryptedError cru do pypdf. Ferramentas que lidam com PDFs protegidos de
    propósito (Proteger/Remover senha) não usam este helper; leem o PdfReader diretamente.
    """
    reader = PdfReader(input_path)
    if not reader.is_encrypted:
        return reader

    password = known_password(input_path)
    access = reader.decrypt(password) if password else PasswordType.NOT_DECRYPTED
    if access == PasswordType.NOT_DECRYPTED:
        access = reader.decrypt("")
        password = None
    if access == PasswordType.NOT_DECRYPTED:
        raise EncryptedPDFError(_LOCKED_MESSAGE)

    if purpose == MODIFY:
        raise RestrictedPDFError(_PROTECTED_MODIFY_MESSAGE if password else _RESTRICTED_MODIFY_MESSAGE)
    if purpose in (EXTRACT, PRINT) and access != PasswordType.OWNER_PASSWORD:
        permissions = reader.user_access_permissions
        if purpose == EXTRACT and permissions is not None and not permissions & UserAccessPermissions.EXTRACT:
            raise RestrictedPDFError(_EXTRACT_DENIED_MESSAGE)
        if purpose == PRINT and permissions is not None and not permissions & UserAccessPermissions.PRINT:
            raise RestrictedPDFError(_PRINT_DENIED_MESSAGE)
    return reader


def open_pdfium(input_path: str) -> pdfium.PdfDocument:
    """Abre o documento no pdfium usando a senha conhecida (se houver), para renderizar ou
    ler texto de PDFs que o usuário já abriu no visualizador."""
    return pdfium.PdfDocument(input_path, password=known_password(input_path))


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


def add_object(writer: PdfWriter, obj):
    """Registra `obj` como objeto indireto do `writer` e devolve a referência.

    O pypdf não tem API pública para isso; o acesso à API privada fica concentrado aqui e
    em `replace_object`, para que uma mudança no pypdf quebre um lugar só."""
    return writer._add_object(obj)


def replace_object(writer: PdfWriter, reference, obj) -> None:
    """Põe `obj` no lugar do objeto indireto `reference` do `writer`: quem aponta para a
    referência (páginas, formulários) passa a ver o objeto novo."""
    writer._replace_object(reference, obj)


# Uma página de 200 x 200 polegadas (o máximo do formato) a 300 DPI dá 3,6 bilhões de pixels,
# uns 14 GB de memória para renderizar: um PDF malicioso derrubaria o app. Acima disto, a
# página é renderizada com menos resolução (100 milhões de pixels são um A0 a 250 DPI).
MAX_RENDER_PIXELS = 100_000_000


def render_scale(pdfium_page, scale: float) -> float:
    """`scale`, ou a escala menor que mantém a imagem da página em `MAX_RENDER_PIXELS`."""
    width, height = pdfium_page.get_size()
    pixels = width * height * scale * scale
    return scale if pixels <= MAX_RENDER_PIXELS else scale * math.sqrt(MAX_RENDER_PIXELS / pixels)


def write_pdf(writer: PdfWriter, output_path: str) -> None:
    """Grava o PDF de forma atômica (ver `atomic_output`)."""
    with atomic_output(output_path) as temp_path:
        with open(temp_path, "wb") as f:
            writer.write(f)


def require_valid_page_index(total_pages: int, index: int, *, label: str = "Página") -> None:
    """Levanta um ValueError claro se `index` (contado a partir de 0) não for uma página do
    documento. A mensagem fala em páginas contadas a partir de 1, como o usuário as vê."""
    if not 0 <= index < total_pages:
        raise ValueError(
            plural_message(
                total_pages,
                "{label} {page} não existe: o documento tem 1 página.",
                "{label} {page} não existe: o documento tem {count} páginas.",
                label=Message(label),
                page=index + 1,
            )
        )
