"""O que vale avisar sobre um PDF ao abri-lo (M14): proteção, assinaturas, formulário e
camadas. Leitura rápida, só da estrutura (sem validar assinaturas)."""

from dataclasses import dataclass, field

from pypdf.constants import UserAccessPermissions

from .base import READ, EncryptedPDFError, open_reader
from .messages import Message


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
