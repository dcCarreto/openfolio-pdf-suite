"""O que o visualizador lê da estrutura do PDF além das páginas: avisos, campos de
formulário, sumário e anexos.

Nada disso é preciso para mostrar a primeira página, e tudo é lido com o pypdf (Python
puro): antes vinha na thread da interface, antes da página aparecer, e o arquivo era lido
inteiro uma vez para cada coisa. Agora é uma leitura só (`core.base.shared_reader`), numa
thread própria; os avisos, o sumário e os destaques dos campos aparecem logo depois da página.
"""

import logging
import threading
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from core.attachments import AttachmentInfo, ListAttachments
from core.base import shared_reader
from core.bookmarks import ListOutline, OutlineItem
from core.document_info import DocumentNotices, InitialView, document_notices, initial_view
from core.form_fields import FormWidget, ListFormWidgets
from ui.thread_relay import ensure_relay, post

logger = logging.getLogger(__name__)


@dataclass
class DocumentDetails:
    notices: DocumentNotices = field(default_factory=DocumentNotices)
    form_widgets: list[FormWidget] = field(default_factory=list)
    outline: list[OutlineItem] = field(default_factory=list)
    attachments: list[AttachmentInfo] = field(default_factory=list)


def read_initial_view(path: str) -> InitialView:
    """Como o PDF pede para ser aberto, lendo do arquivo só o necessário."""
    try:
        with shared_reader(path):
            return initial_view(path)
    except OSError:
        return InitialView()


def read_form_widgets(path: str) -> list[FormWidget]:
    try:
        with shared_reader(path):
            return ListFormWidgets().run(path)
    except Exception:
        return []  # um formulário malformado não impede de ver o PDF


def read_details(path: str) -> DocumentDetails:
    """Tudo numa leitura só do arquivo. Uma parte ilegível fica vazia; o resto aparece."""
    details = DocumentDetails()
    try:
        with shared_reader(path):
            details.notices = document_notices(path)
            for name, reader in (
                ("form_widgets", ListFormWidgets().run),
                ("outline", ListOutline().run),
                ("attachments", ListAttachments().run),
            ):
                try:
                    setattr(details, name, reader(path))
                except Exception:
                    logger.debug("Sem %s legível em %s", name, path, exc_info=True)
    except OSError:
        logger.debug("Não foi possível ler %s", path, exc_info=True)
    return details


class DetailsLoader(QObject):
    """Lê os detalhes numa thread; `loaded(pedido, detalhes)` chega na thread da interface.
    Só o último pedido interessa: quem pede compara o número com o que `load` devolveu."""

    loaded = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_relay()
        self._request = 0

    def load(self, path: str) -> int:
        self._request += 1
        request = self._request
        threading.Thread(target=self._run, args=(request, path), name="openfolio-details", daemon=True).start()
        return request

    def _run(self, request: int, path: str) -> None:
        details = read_details(path)
        post(self, "loaded", request, details)  # se o visualizador já fechou, não chega
