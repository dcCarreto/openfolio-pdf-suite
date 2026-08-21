"""Anexos embutidos (`/Names/EmbeddedFiles`) em arquivos PDF: listar, adicionar, remover
e extrair."""

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


class ExtractAttachments(PDFOperation):
    """Extrai todos os anexos embutidos de um PDF para uma pasta local."""

    def run(self, input_path: str, output_dir: str) -> list[str]:
        reader = open_reader(input_path)
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for name, contents in reader.attachments.items():
            output_path = output_dir_path / name
            output_path.write_bytes(contents[0])
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
