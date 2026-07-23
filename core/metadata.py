"""Metadados de arquivos PDF."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class ReadMetadata(PDFOperation):
    """Lê os metadados de um PDF."""

    def run(self, input_path: str) -> dict:
        reader = PdfReader(input_path)
        metadata = reader.metadata or {}
        return {
            "title": metadata.get("/Title", "") or "",
            "author": metadata.get("/Author", "") or "",
            "subject": metadata.get("/Subject", "") or "",
            "keywords": metadata.get("/Keywords", "") or "",
        }


class SetMetadata(PDFOperation):
    """Atualiza os metadados de um PDF."""

    def run(
        self,
        input_path: str,
        output_path: str,
        title: str = "",
        author: str = "",
        subject: str = "",
        keywords: str = "",
    ) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.add_metadata(
            {
                "/Title": title,
                "/Author": author,
                "/Subject": subject,
                "/Keywords": keywords,
            }
        )

        with open(output_path, "wb") as f:
            writer.write(f)
