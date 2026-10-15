"""Anexos embutidos (`/Names/EmbeddedFiles`) em arquivos PDF: listar, adicionar, remover
e extrair."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, NameObject

from .base import PDFOperation, open_reader


@dataclass
class AttachmentInfo:
    name: str
    size: int


class ListAttachments(PDFOperation):
    """Lista os anexos embutidos num PDF, com nome e tamanho em bytes."""

    def run(self, input_path: str) -> list[AttachmentInfo]:
        reader = open_reader(input_path)
        return [
            AttachmentInfo(name=name, size=len(contents[0]))
            for name, contents in reader.attachments.items()
        ]


class AddAttachment(PDFOperation):
    """Embute um arquivo local num PDF."""

    def run(self, input_path: str, output_path: str, attachment_path: str) -> None:
        open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        writer = PdfWriter(clone_from=input_path)
        data = Path(attachment_path).read_bytes()
        writer.add_attachment(Path(attachment_path).name, data)

        with open(output_path, "wb") as f:
            writer.write(f)


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_FILENAME_LENGTH = 180


def safe_attachment_filename(name: str) -> str:
    """Transforma o nome de um anexo (que vem de dentro do PDF, ou seja, de quem fez o
    arquivo) num nome de arquivo simples e seguro.

    Sem isto, um anexo chamado `../../algo` ou `C:\\pasta\\algo` seria gravado fora da pasta
    escolhida — o PDF decidiria onde escrever no disco de quem o abre. Só o último
    componente do nome é aproveitado (aceitando `/` e `\\` como separadores, qualquer que
    seja o sistema), sem caracteres inválidos no Windows e sem nomes reservados.
    """
    base = re.split(r"[\\/]", str(name))[-1]
    base = re.sub(r'[\x00-\x1f<>:"|?*]', "_", base).strip().rstrip(". ")
    if base in ("", ".", ".."):
        base = "anexo"
    stem, extension = os.path.splitext(base)
    if stem.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    if len(stem) + len(extension) > _MAX_FILENAME_LENGTH:
        extension = extension[:20]
        stem = stem[: _MAX_FILENAME_LENGTH - len(extension)]
    return stem + extension


def _unique_path(directory: Path, filename: str, used: set[str]) -> Path:
    stem, extension = os.path.splitext(filename)
    candidate = filename
    counter = 2
    while candidate.casefold() in used or (directory / candidate).exists():
        candidate = f"{stem} ({counter}){extension}"
        counter += 1
    used.add(candidate.casefold())
    return directory / candidate


class ExtractAttachments(PDFOperation):
    """Extrai todos os anexos embutidos de um PDF para uma pasta local.

    Os nomes passam por `safe_attachment_filename`; anexos com o mesmo nome (ou com o nome
    de um arquivo que já existe na pasta) ganham um sufixo " (2)", " (3)"... em vez de
    sobrescrever o que já estava lá.
    """

    def run(self, input_path: str, output_dir: str) -> list[str]:
        reader = open_reader(input_path)
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        resolved_dir = output_dir_path.resolve()

        output_paths = []
        used: set[str] = set()
        for name, contents in reader.attachments.items():
            for content in contents:
                output_path = _unique_path(output_dir_path, safe_attachment_filename(name), used)
                if not output_path.resolve().is_relative_to(resolved_dir):
                    raise ValueError(f'O anexo "{name}" tentou gravar fora da pasta escolhida.')
                output_path.write_bytes(content)
                output_paths.append(str(output_path))
        return output_paths


class RemoveAttachment(PDFOperation):
    """Remove um anexo embutido de um PDF pelo nome (ver `ListAttachments`)."""

    def run(self, input_path: str, output_path: str, name: str) -> None:
        reader = open_reader(input_path)
        if name not in reader.attachments:
            raise ValueError(f'Nenhum anexo chamado "{name}" foi encontrado neste PDF.')

        writer = PdfWriter(clone_from=input_path)
        catalog = writer.root_object
        names_dict_ref = catalog.get("/Names")
        if names_dict_ref is None:
            raise ValueError(f'Nenhum anexo chamado "{name}" foi encontrado neste PDF.')
        names_dict = names_dict_ref.get_object()
        embedded_files_ref = names_dict.get("/EmbeddedFiles")
        if embedded_files_ref is None:
            raise ValueError(f'Nenhum anexo chamado "{name}" foi encontrado neste PDF.')
        embedded_files = embedded_files_ref.get_object()
        names_array = embedded_files.get("/Names") or []

        remaining = ArrayObject()
        skip_next = False
        for entry in names_array:
            if skip_next:
                skip_next = False
                continue
            entry_obj = entry.get_object() if hasattr(entry, "get_object") else entry
            if isinstance(entry_obj, str) and entry_obj == name:
                skip_next = True
                continue
            remaining.append(entry)
        embedded_files[NameObject("/Names")] = remaining

        with open(output_path, "wb") as f:
            writer.write(f)
