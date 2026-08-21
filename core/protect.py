"""Proteção por senha e permissões de arquivos PDF."""

from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions as _Perm

from .base import PDFOperation, open_reader


@dataclass
class PDFPermissions:
    """Permissões concedidas a quem abre o PDF só com a senha de usuário (sem a senha de
    proprietário). Todas começam liberadas — mesmo comportamento de `ProtectPDF` antes
    destas permissões existirem — e cada uma vira um bit da permissions_flag do pypdf."""

    allow_printing: bool = True
    allow_high_quality_printing: bool = True
    allow_modify: bool = True
    allow_assembly: bool = True
    allow_copy: bool = True
    allow_copy_for_accessibility: bool = True
    allow_annotations: bool = True
    allow_fill_forms: bool = True

    def as_flag(self) -> int:
        flag = 0
        if self.allow_printing:
            flag |= _Perm.PRINT
        if self.allow_high_quality_printing:
            flag |= _Perm.PRINT_TO_REPRESENTATION
        if self.allow_modify:
            flag |= _Perm.MODIFY
        if self.allow_assembly:
            flag |= _Perm.ASSEMBLE_DOC
        if self.allow_copy:
            flag |= _Perm.EXTRACT
        if self.allow_copy_for_accessibility:
            flag |= _Perm.EXTRACT_TEXT_AND_GRAPHICS
        if self.allow_annotations:
            flag |= _Perm.ADD_OR_MODIFY
        if self.allow_fill_forms:
            flag |= _Perm.FILL_FORM_FIELDS
        return flag


class ProtectPDF(PDFOperation):
    """Protege um PDF com senha e, opcionalmente, restringe o que pode ser feito com ele.

    `owner_password` é a "senha de permissões" do PDF: quem só tem `password` (a senha de
    usuário, que pode inclusive ficar vazia para não pedir senha na abertura) fica limitado
    pelo `permissions` informado; quem sabe a senha de proprietário sempre tem acesso total,
    do mesmo jeito que o Acrobat separa "Senha para abrir o documento" de "Senha de
    permissões" nas propriedades de segurança.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        password: str,
        owner_password: str | None = None,
        permissions: PDFPermissions | None = None,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        encrypt_kwargs = {"user_password": password, "algorithm": "AES-256"}
        if owner_password:
            encrypt_kwargs["owner_password"] = owner_password
        if permissions is not None:
            encrypt_kwargs["permissions_flag"] = permissions.as_flag()
        writer.encrypt(**encrypt_kwargs)

        with open(output_path, "wb") as f:
            writer.write(f)


class UnlockPDF(PDFOperation):
    """Remove a senha de um PDF protegido."""

    def run(self, input_path: str, output_path: str, password: str) -> None:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            if not reader.decrypt(password):
                raise ValueError("Senha incorreta.")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
