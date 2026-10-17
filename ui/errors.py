"""Mensagens de erro para o usuário (M03).

Antes o texto da exceção aparecia cru ("[Errno 13] Permission denied: 'C:\\...'",
"PdfReadError: EOF marker not found"). Agora as exceções conhecidas viram uma frase que diz
o que aconteceu e o que fazer; o texto técnico fica atrás de "Mostrar detalhes" no diálogo,
para quem quiser copiar numa issue.
"""

import errno
import traceback
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from ui.i18n import error_text, tr


def _technical(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()


def describe_error(exc: BaseException) -> tuple[str, str | None]:
    """(mensagem para o usuário, detalhes técnicos ou None)."""
    from pypdf.errors import PdfReadError, PdfStreamError

    name = Path(getattr(exc, "filename", "") or "").name
    if isinstance(exc, FileNotFoundError):
        return tr("O arquivo não foi encontrado: {name}").format(name=name or "?"), str(exc)
    if isinstance(exc, PermissionError):
        return (
            tr(
                "Sem permissão para usar o arquivo {name}. Se ele estiver aberto em outro programa, "
                "feche-o e tente de novo."
            ).format(name=name or ""),
            str(exc),
        )
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return tr("Não há espaço livre no disco para gravar o arquivo."), str(exc)
    if isinstance(exc, MemoryError):
        return tr("Memória insuficiente para concluir a operação. Feche outros programas ou use um arquivo menor."), None
    if isinstance(exc, (PdfReadError, PdfStreamError)) or type(exc).__name__ == "PdfiumError":
        return tr("O PDF parece estar corrompido ou não é um PDF válido."), _technical(exc)
    if isinstance(exc, (ValueError, RuntimeError)) and exc.args and isinstance(exc.args[0], str):
        return error_text(exc), None  # mensagens do próprio app, já escritas para o usuário
    return tr("Ocorreu um erro inesperado."), _technical(exc)


def show_error(parent, title: str, template: str, exc: BaseException) -> None:
    """Diálogo de erro: `template` (já traduzido, com `{error}`) com a mensagem amigável, e
    o texto técnico em "Mostrar detalhes" quando houver."""
    message, details = describe_error(exc)
    text = template.format(error=message)
    if not details:
        QMessageBox.critical(parent, title, text)
        return
    box = QMessageBox(QMessageBox.Icon.Critical, title, text, QMessageBox.StandardButton.Ok, parent)
    box.setDetailedText(details)
    box.exec()
