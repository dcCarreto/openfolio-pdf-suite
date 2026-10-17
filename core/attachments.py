"""Anexos embutidos (`/Names/EmbeddedFiles`) em arquivos PDF: listar, adicionar, remover
e extrair."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from .base import READ, PDFOperation, atomic_output, open_reader, write_pdf
from .document import build_name_tree, iter_name_tree, unique_name
from .messages import Message


@dataclass
class AttachmentInfo:
    name: str
    size: int


class ListAttachments(PDFOperation):
    """Lista os anexos embutidos num PDF, com nome e tamanho em bytes."""

    def run(self, input_path: str) -> list[AttachmentInfo]:
        reader = open_reader(input_path, purpose=READ)
        return [
            AttachmentInfo(name=name, size=len(contents[0]))
            for name, contents in reader.attachments.items()
        ]


class AddAttachment(PDFOperation):
    """Embute um arquivo local num PDF. Se já houver um anexo com o mesmo nome, o novo
    ganha um sufixo (" (2)"...) — nomes repetidos deixariam a árvore de anexos ambígua.
    Devolve o nome com que o arquivo foi anexado."""

    def run(self, input_path: str, output_path: str, attachment_path: str) -> str:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        used = {str(key) for key, _value in _embedded_file_entries(writer)}
        name = unique_name(Path(attachment_path).name, used)
        writer.add_attachment(name, Path(attachment_path).read_bytes())
        write_pdf(writer, output_path)
        return name


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
        reader = open_reader(input_path, purpose=READ)
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        resolved_dir = output_dir_path.resolve()

        output_paths = []
        used: set[str] = set()
        for name, contents in reader.attachments.items():
            for content in contents:
                output_path = _unique_path(output_dir_path, safe_attachment_filename(name), used)
                if not output_path.resolve().is_relative_to(resolved_dir):
                    raise ValueError(Message('O anexo "{name}" tentou gravar fora da pasta escolhida.', name=name))
                output_path.write_bytes(content)
                output_paths.append(str(output_path))
        return output_paths


class SaveAttachment(PDFOperation):
    """Grava um anexo (o primeiro com esse nome) em `output_path`, escolhido pelo usuário
    num diálogo — usado pelo painel de anexos do visualizador."""

    def run(self, input_path: str, name: str, output_path: str) -> str:
        reader = open_reader(input_path, purpose=READ)
        contents = reader.attachments.get(name)
        if not contents:
            raise ValueError(Message('Nenhum anexo chamado "{name}" foi encontrado neste PDF.', name=name))
        with atomic_output(output_path) as temp_path:
            Path(temp_path).write_bytes(contents[0])
        return output_path


def _embedded_file_entries(document) -> list[tuple[object, object]]:
    names = document.root_object.get("/Names")
    names = names.get_object() if names is not None else None
    if not isinstance(names, DictionaryObject) or "/EmbeddedFiles" not in names:
        return []
    return list(iter_name_tree(names.raw_get("/EmbeddedFiles")))


def _filespec_names(filespec) -> set[str]:
    spec = filespec.get_object()
    return {str(spec[key]) for key in ("/UF", "/F") if isinstance(spec, DictionaryObject) and key in spec}


class RemoveAttachment(PDFOperation):
    """Remove um anexo embutido de um PDF pelo nome (ver `ListAttachments`).

    A árvore de anexos pode ter vários níveis (`/Kids`), comum em PDFs com muitos anexos;
    ela é percorrida inteira e regravada sem o anexo. O nome pode ser a chave da árvore ou
    o nome de arquivo do anexo (`/UF`/`/F`), que é o que a listagem mostra quando os dois
    diferem. Depois de gravar, confere que o anexo realmente saiu.
    """

    def run(self, input_path: str, output_path: str, name: str) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        entries = _embedded_file_entries(writer)
        remaining = [
            (str(key), filespec)
            for key, filespec in entries
            if str(key) != name and name not in _filespec_names(filespec)
        ]
        if len(remaining) == len(entries):
            raise ValueError(Message('Nenhum anexo chamado "{name}" foi encontrado neste PDF.', name=name))

        names = writer.root_object["/Names"].get_object()
        if remaining:
            names[NameObject("/EmbeddedFiles")] = build_name_tree(remaining)
        else:
            del names["/EmbeddedFiles"]
        with atomic_output(output_path) as temp_path:
            with open(temp_path, "wb") as f:
                writer.write(f)
            if name in PdfReader(temp_path).attachments:
                raise RuntimeError(Message('O anexo "{name}" continuaria no arquivo; nada foi salvo.', name=name))
