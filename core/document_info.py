"""O que vale avisar sobre um PDF ao abri-lo (M14): proteção, assinaturas, formulário e
camadas. Leitura rápida, só da estrutura (sem validar assinaturas)."""

import logging
from dataclasses import dataclass, field

from pypdf.constants import UserAccessPermissions
from pypdf.generic import ArrayObject, Destination, DictionaryObject, Fit, NullObject

from .base import READ, EncryptedPDFError, open_reader
from .messages import Message

logger = logging.getLogger(__name__)


# O tipo de cada aviso, que define a cor da faixa e o botão dela.
PROTECTED, SIGNED, FORM, LAYERS = "protected", "signed", "form", "layers"


@dataclass
class DocumentNotices:
    messages: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)  # um por mensagem: PROTECTED, SIGNED, FORM ou LAYERS
    signature_count: int = 0

    def add(self, kind: str, message) -> None:
        self.kinds.append(kind)
        self.messages.append(message)


@dataclass
class InitialView:
    """Como o próprio PDF pede para ser aberto (/OpenAction, /PageLayout e /PageMode)."""

    page: int = 0
    top: float | None = None
    layout: str = ""  # "single", "continuous", "double", "book" ou "": o PDF não diz
    panel: str = ""  # "pages", "outline", "attachments" ou "": o PDF não diz


_LAYOUTS = {
    "/SinglePage": "single",
    "/OneColumn": "continuous",
    "/TwoColumnLeft": "double",
    "/TwoPageLeft": "double",
    "/TwoColumnRight": "book",
    "/TwoPageRight": "book",
}
_PANELS = {"/UseThumbs": "pages", "/UseOutlines": "outline", "/UseAttachments": "attachments"}


def initial_view(path: str) -> InitialView:
    """Só leitura da estrutura; um PDF malformado abre como qualquer outro. /PageMode /FullScreen
    fica de fora: um arquivo não toma a tela sem o usuário pedir."""
    view = InitialView()
    try:
        reader = open_reader(path, purpose=READ)
        view.layout = _LAYOUTS.get(str(reader.page_layout), "")
        view.panel = _PANELS.get(str(reader.page_mode), "")
        destination = reader.open_destination
        if destination is None:  # a outra forma de /OpenAction: uma ação /GoTo
            action = reader.root_object.get("/OpenAction")
            action = action.get_object() if action is not None else None
            if isinstance(action, DictionaryObject) and action.get("/S") == "/GoTo":
                target = action.get("/D")
                if isinstance(target, ArrayObject):
                    page, kind, *values = target
                    destination = Destination("OpenAction", page, Fit(kind, tuple(values)))
                else:
                    destination = target
        if isinstance(destination, str):  # um destino com nome
            destination = reader.named_destinations.get(str(destination))
        if isinstance(destination, Destination):
            page = reader.get_destination_page_number(destination)
            if page is not None and page >= 0:
                view.page = page
                top = destination.top
                view.top = None if top is None or isinstance(top, NullObject) else float(top)
    except Exception:
        logger.debug("Visão inicial ilegível em %s", path, exc_info=True)
    return view


def document_notices(path: str) -> DocumentNotices:
    notices = DocumentNotices()
    try:
        reader = open_reader(path, purpose=READ)
    except EncryptedPDFError:
        notices.add(PROTECTED, Message("Protegido por senha."))
        return notices
    except Exception:
        return notices

    if reader.is_encrypted:
        permissions = reader.user_access_permissions
        restricted = permissions is not None and not (
            permissions & UserAccessPermissions.MODIFY and permissions & UserAccessPermissions.EXTRACT
        )
        if restricted:
            notices.add(PROTECTED, Message("Protegido: o autor bloqueou alterações ou cópia."))
        else:
            notices.add(PROTECTED, Message("Protegido por senha."))

    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}
    signatures = [f for f in fields.values() if f.field_type == "/Sig" and f.value is not None]
    fillable = [f for f in fields.values() if f.field_type not in (None, "/Sig")]
    notices.signature_count = len(signatures)
    # Só a estrutura: a validade de cada assinatura sai do "Ver" (verificação completa).
    if len(signatures) == 1:
        notices.add(SIGNED, Message("1 assinatura digital. Alterar o PDF a invalida."))
    elif signatures:
        notices.add(SIGNED, Message("{count} assinaturas digitais. Alterar o PDF as invalida.", count=len(signatures)))
    if fillable:
        notices.add(FORM, Message("Este PDF tem campos de formulário. Clique em um campo para preencher."))
    if "/OCProperties" in reader.root_object:
        notices.add(LAYERS, Message("Este PDF tem camadas: partes que podem ser mostradas ou ocultadas."))
    return notices
