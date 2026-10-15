"""Metadados de arquivos PDF."""

from pypdf import PdfWriter

from .base import READ, PDFOperation, open_reader, write_pdf


class ReadMetadata(PDFOperation):
    """Lê os metadados de um PDF."""

    def run(self, input_path: str) -> dict:
        reader = open_reader(input_path, purpose=READ)
        metadata = reader.metadata or {}
        return {
            "title": metadata.get("/Title", "") or "",
            "author": metadata.get("/Author", "") or "",
            "subject": metadata.get("/Subject", "") or "",
            "keywords": metadata.get("/Keywords", "") or "",
        }


class SetMetadata(PDFOperation):
    """Atualiza os metadados de um PDF.

    Campos não informados (None) preservam o valor já existente no documento;
    para apagar um campo, passe uma string vazia explicitamente.

    Os metadados existem em dois lugares: no dicionário `/Info` e, em muitos PDFs, no XMP
    (`/Metadata` do catálogo) — e leitores como o Acrobat preferem o XMP quando ele existe.
    Atualizar só o `/Info` faria o título novo aparecer num leitor e o antigo em outro,
    então o XMP, se existir, recebe os mesmos valores.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        title: str | None = None,
        author: str | None = None,
        subject: str | None = None,
        keywords: str | None = None,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        existing = reader.metadata or {}

        def resolved(value: str | None, key: str) -> str:
            return (existing.get(key) or "") if value is None else value

        writer.add_metadata(
            {
                "/Title": resolved(title, "/Title"),
                "/Author": resolved(author, "/Author"),
                "/Subject": resolved(subject, "/Subject"),
                "/Keywords": resolved(keywords, "/Keywords"),
            }
        )
        _sync_xmp(writer, title, author, subject, keywords)
        write_pdf(writer, output_path)


def _sync_xmp(writer: PdfWriter, title, author, subject, keywords) -> None:
    xmp = writer.xmp_metadata
    if xmp is None:
        return
    if title is not None:
        xmp.dc_title = {"x-default": title} if title else None
    if author is not None:
        xmp.dc_creator = [author] if author else None
    if subject is not None:
        xmp.dc_description = {"x-default": subject} if subject else None
    if keywords is not None:
        xmp.pdf_keywords = keywords or None
    writer.xmp_metadata = xmp
