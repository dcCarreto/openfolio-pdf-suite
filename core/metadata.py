"""Metadados de arquivos PDF."""

import datetime

from pypdf import PdfWriter

from .base import READ, PDFOperation, open_reader, write_pdf

# Campos editáveis: chave usada aqui -> chave do dicionário Info.
_FIELDS = {
    "title": "/Title",
    "author": "/Author",
    "subject": "/Subject",
    "keywords": "/Keywords",
    "creator": "/Creator",  # aplicativo em que o documento foi criado
    "producer": "/Producer",  # aplicativo que gerou o PDF
}


def _parse_pdf_date(value) -> datetime.datetime | None:
    text = str(value or "")
    if not text.startswith("D:"):
        return None
    digits = text[2:16]
    try:
        moment = datetime.datetime.strptime(digits.ljust(14, "0")[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    rest = text[16:].replace("'", "")
    if rest[:1] in ("+", "-") and len(rest) >= 3:
        hours, minutes = int(rest[1:3]), int(rest[3:5] or 0)
        offset = datetime.timedelta(hours=hours, minutes=minutes)
        return moment.replace(tzinfo=datetime.timezone(offset if rest[0] == "+" else -offset))
    if rest[:1] in ("Z", "z"):
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def _pdf_date(moment: datetime.datetime) -> str:
    offset = moment.utcoffset() or datetime.timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return moment.strftime("D:%Y%m%d%H%M%S") + f"{sign}{minutes // 60:02d}'{minutes % 60:02d}'"


class ReadMetadata(PDFOperation):
    """Lê os metadados de um PDF: os campos editáveis (texto) e as datas de criação e de
    modificação (`datetime`, ou None se o PDF não as tiver)."""

    def run(self, input_path: str) -> dict:
        reader = open_reader(input_path, purpose=READ)
        metadata = reader.metadata or {}
        result = {name: str(metadata.get(key, "") or "") for name, key in _FIELDS.items()}
        result["created"] = _parse_pdf_date(metadata.get("/CreationDate"))
        result["modified"] = _parse_pdf_date(metadata.get("/ModDate"))
        return result


class SetMetadata(PDFOperation):
    """Atualiza os metadados de um PDF.

    Campos não informados (None) preservam o valor já existente no documento;
    para apagar um campo, passe uma string vazia explicitamente. A data de modificação
    passa a ser a de agora.

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
        creator: str | None = None,
        producer: str | None = None,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        existing = reader.metadata or {}
        values = {"title": title, "author": author, "subject": subject, "keywords": keywords, "creator": creator, "producer": producer}

        updated = {
            key: (str(existing.get(key) or "") if values[name] is None else values[name])
            for name, key in _FIELDS.items()
        }
        now = datetime.datetime.now().astimezone().replace(microsecond=0)
        updated["/ModDate"] = _pdf_date(now)
        writer.add_metadata(updated)
        _sync_xmp(writer, values, now)
        write_pdf(writer, output_path)


def _sync_xmp(writer: PdfWriter, values: dict, modified: datetime.datetime) -> None:
    xmp = writer.xmp_metadata
    if xmp is None:
        return
    title, author, subject = values["title"], values["author"], values["subject"]
    if title is not None:
        xmp.dc_title = {"x-default": title} if title else None
    if author is not None:
        xmp.dc_creator = [author] if author else None
    if subject is not None:
        xmp.dc_description = {"x-default": subject} if subject else None
    if values["keywords"] is not None:
        xmp.pdf_keywords = values["keywords"] or None
    if values["creator"] is not None:
        xmp.xmp_creator_tool = values["creator"] or None
    if values["producer"] is not None:
        xmp.pdf_producer = values["producer"] or None
    xmp.xmp_modify_date = modified
    writer.xmp_metadata = xmp
