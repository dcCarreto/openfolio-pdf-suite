"""O que vale avisar sobre um PDF ao abri-lo (M14): proteção, assinaturas, formulário e
camadas. Leitura rápida, só da estrutura (sem validar assinaturas)."""

from dataclasses import dataclass, field

from pypdf.constants import UserAccessPermissions

from .base import READ, EncryptedPDFError, open_reader
from .messages import Message


@dataclass
class DocumentNotices:
    messages: list[str] = field(default_factory=list)
    signature_count: int = 0


def document_notices(path: str) -> DocumentNotices:
    notices = DocumentNotices()
    try:
        reader = open_reader(path, purpose=READ)
    except EncryptedPDFError:
        notices.messages.append(Message("Protegido por senha."))
        return notices
    except Exception:
        return notices

    if reader.is_encrypted:
        permissions = reader.user_access_permissions
        restricted = permissions is not None and not (
            permissions & UserAccessPermissions.MODIFY and permissions & UserAccessPermissions.EXTRACT
        )
        if restricted:
            notices.messages.append(Message("O autor restringiu alterações ou cópia (senha de permissões)."))
        else:
            notices.messages.append(Message("Protegido por senha."))

    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}
    signatures = [f for f in fields.values() if f.field_type == "/Sig" and f.value is not None]
    fillable = [f for f in fields.values() if f.field_type not in (None, "/Sig")]
    notices.signature_count = len(signatures)
    if signatures:
        notices.messages.append(
            Message("Assinado digitalmente ({count} assinatura(s)). Alterar o documento invalida a assinatura.", count=len(signatures))
        )
    if fillable:
        notices.messages.append(Message("Tem formulário ({count} campo(s)).", count=len(fillable)))
    if "/OCProperties" in reader.trailer["/Root"]:
        notices.messages.append(Message("Tem camadas (veja a aba Camadas)."))
    return notices
