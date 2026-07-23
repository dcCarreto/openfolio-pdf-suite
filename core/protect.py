"""Proteção por senha de arquivos PDF."""

from pypdf import PdfReader, PdfWriter

from .base import PDFOperation


class ProtectPDF(PDFOperation):
    """Protege um PDF com senha."""

    def run(self, input_path: str, output_path: str, password: str) -> None:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(user_password=password, algorithm="AES-256")

        with open(output_path, "wb") as f:
            writer.write(f)


class UnlockPDF(PDFOperation):
    """Remove a senha de um PDF protegido."""

    def run(self, input_path: str, output_path: str, password: str) -> None:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            reader.decrypt(password)

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
