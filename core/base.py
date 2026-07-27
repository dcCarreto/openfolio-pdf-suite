"""Classes e helpers base compartilhados pelos módulos de core."""

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


def require_valid_page_index(total_pages: int, index: int, *, label: str = "Página") -> None:
    """Levanta um ValueError claro se `index` não for um índice de página válido."""
    if not 0 <= index < total_pages:
        raise ValueError(
            f"{label} inválida: índice {index} (o documento tem {total_pages} "
            f"página(s), de 0 a {total_pages - 1})."
        )
