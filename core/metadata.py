"""Metadados de arquivos PDF."""

from pypdf import PdfWriter

from .base import PDFOperation, open_reader


class ReadMetadata(PDFOperation):
    """Lê os metadados de um PDF."""

    def run(self, input_path: str) -> dict:
        reader = open_reader(input_path)
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
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

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

        with open(output_path, "wb") as f:
            writer.write(f)
