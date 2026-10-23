"""Testes de core/attachments.py: listar, adicionar, remover e extrair anexos embutidos."""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from core.attachments import (
    AddAttachment,
    ExtractAttachments,
    ListAttachments,
    RemoveAttachment,
    safe_attachment_filename,
)
from core.base import EncryptedPDFError, add_object


def _make_plain_pdf(path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_add_and_list_attachment(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_path = tmp_path / "notas.txt"
    attachment_path.write_bytes(b"conteudo do anexo")
    output_path = tmp_path / "out.pdf"

    AddAttachment().run(str(pdf_path), str(output_path), str(attachment_path))

    attachments = ListAttachments().run(str(output_path))
    assert len(attachments) == 1
    assert attachments[0].name == "notas.txt"
    assert attachments[0].size == len(b"conteudo do anexo")


def test_list_attachments_empty_for_pdf_without_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    assert ListAttachments().run(str(pdf_path)) == []


def test_list_attachments_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ListAttachments().run(str(encrypted_path))


def test_add_attachment_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    attachment_path = tmp_path / "notas.txt"
    attachment_path.write_bytes(b"x")

    with pytest.raises(EncryptedPDFError):
        AddAttachment().run(str(encrypted_path), str(tmp_path / "out.pdf"), str(attachment_path))


def test_extract_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_path = tmp_path / "dados.csv"
    attachment_path.write_bytes(b"a,b,c\n1,2,3")
    with_attachment = tmp_path / "with_attachment.pdf"
    AddAttachment().run(str(pdf_path), str(with_attachment), str(attachment_path))

    output_dir = tmp_path / "extracted"
    output_paths = ExtractAttachments().run(str(with_attachment), str(output_dir))

    assert len(output_paths) == 1
    from pathlib import Path
    assert Path(output_paths[0]).read_bytes() == b"a,b,c\n1,2,3"


def test_extract_attachments_empty_for_pdf_without_attachments(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    assert ExtractAttachments().run(str(pdf_path), str(tmp_path / "out")) == []


def test_remove_attachment(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_a = tmp_path / "a.txt"
    attachment_a.write_bytes(b"A")
    attachment_b = tmp_path / "b.txt"
    attachment_b.write_bytes(b"B")

    step1 = tmp_path / "step1.pdf"
    AddAttachment().run(str(pdf_path), str(step1), str(attachment_a))
    step2 = tmp_path / "step2.pdf"
    AddAttachment().run(str(step1), str(step2), str(attachment_b))

    output_path = tmp_path / "out.pdf"
    RemoveAttachment().run(str(step2), str(output_path), name="a.txt")

    attachments = ListAttachments().run(str(output_path))
    assert [a.name for a in attachments] == ["b.txt"]


def test_remove_attachment_rejects_unknown_name(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    with pytest.raises(ValueError):
        RemoveAttachment().run(str(pdf_path), str(tmp_path / "out.pdf"), name="inexistente.txt")


def test_remove_attachment_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        RemoveAttachment().run(str(encrypted_path), str(tmp_path / "out.pdf"), name="x.txt")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("notas.txt", "notas.txt"),
        ("../../fora.txt", "fora.txt"),
        ("..\\..\\fora.txt", "fora.txt"),
        ("C:\\Windows\\System32\\x.dll", "x.dll"),
        ("/etc/passwd", "passwd"),
        ("..", "anexo"),
        ("", "anexo"),
        ("CON.txt", "_CON.txt"),
        ("nul", "_nul"),
        ('a<b>c:d"e|f?g*h.txt', "a_b_c_d_e_f_g_h.txt"),
        ("relatorio.pdf. . ", "relatorio.pdf"),
    ],
)
def test_safe_attachment_filename(name, expected):
    assert safe_attachment_filename(name) == expected


def test_extract_attachments_never_writes_outside_the_chosen_folder(tmp_path):
    # O nome do anexo vem de dentro do PDF: um arquivo malicioso não pode escolher onde
    # gravar no disco de quem o abre.
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    writer = PdfWriter(clone_from=str(pdf_path))
    hostile_names = ["../../fora.txt", "..\\..\\fora_windows.txt", str(tmp_path / "absoluto.txt"), "/tmp/raiz.txt"]
    for index, name in enumerate(hostile_names):
        writer.add_attachment(name, f"conteudo {index}".encode())
    malicious = tmp_path / "malicious.pdf"
    with open(malicious, "wb") as f:
        writer.write(f)

    output_dir = tmp_path / "saida" / "sub"
    output_paths = ExtractAttachments().run(str(malicious), str(output_dir))

    assert len(output_paths) == len(hostile_names)
    resolved_dir = output_dir.resolve()
    assert all(Path(path).resolve().parent == resolved_dir for path in output_paths)
    assert not (tmp_path / "fora.txt").exists()
    assert not (tmp_path / "fora_windows.txt").exists()
    assert not (tmp_path / "absoluto.txt").exists()


def test_extract_attachments_does_not_overwrite_duplicates_or_existing_files(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    writer = PdfWriter(clone_from=str(pdf_path))
    writer.add_attachment("dados.txt", b"primeiro")
    writer.add_attachment("dados.txt", b"segundo")
    with_attachments = tmp_path / "with.pdf"
    with open(with_attachments, "wb") as f:
        writer.write(f)

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "dados.txt").write_bytes(b"ja estava aqui")

    output_paths = ExtractAttachments().run(str(with_attachments), str(output_dir))

    assert (output_dir / "dados.txt").read_bytes() == b"ja estava aqui"
    assert sorted(Path(path).name for path in output_paths) == ["dados (2).txt", "dados (3).txt"]
    assert sorted(Path(path).read_bytes() for path in output_paths) == [b"primeiro", b"segundo"]


def _pdf_with_attachment_in_kids(tmp_path, key: str, filename: str):
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject

    pdf_path = tmp_path / "base.pdf"
    _make_plain_pdf(pdf_path)
    writer = PdfWriter(clone_from=str(pdf_path))
    embedded = DecodedStreamObject()
    embedded.set_data(b"abc")
    embedded[NameObject("/Type")] = NameObject("/EmbeddedFile")
    filespec = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): TextStringObject(filename),
            NameObject("/UF"): TextStringObject(filename),
            NameObject("/EF"): DictionaryObject({NameObject("/F"): add_object(writer, embedded)}),
        }
    )
    leaf = DictionaryObject(
        {
            NameObject("/Names"): ArrayObject([TextStringObject(key), add_object(writer, filespec)]),
            NameObject("/Limits"): ArrayObject([TextStringObject(key), TextStringObject(key)]),
        }
    )
    writer.root_object[NameObject("/Names")] = DictionaryObject(
        {NameObject("/EmbeddedFiles"): DictionaryObject({NameObject("/Kids"): ArrayObject([add_object(writer, leaf)])})}
    )
    path = tmp_path / "kids.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_remove_attachment_inside_a_multilevel_name_tree(tmp_path):
    # A remoção só olhava o primeiro nível da árvore e dizia que tinha removido.
    pdf_path = _pdf_with_attachment_in_kids(tmp_path, "a.txt", "a.txt")
    output_path = tmp_path / "out.pdf"

    RemoveAttachment().run(str(pdf_path), str(output_path), name="a.txt")

    assert ListAttachments().run(str(output_path)) == []


def test_remove_attachment_by_its_file_name_when_the_tree_key_differs(tmp_path):
    pdf_path = _pdf_with_attachment_in_kids(tmp_path, "anexo1", "relatorio.xlsx")
    output_path = tmp_path / "out.pdf"

    RemoveAttachment().run(str(pdf_path), str(output_path), name="relatorio.xlsx")

    assert PdfReader(str(output_path)).attachments == {}


def test_add_attachment_with_existing_name_gets_a_suffix(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)
    attachment_path = tmp_path / "notas.txt"
    attachment_path.write_bytes(b"1")
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"

    AddAttachment().run(str(pdf_path), str(first), str(attachment_path))
    name = AddAttachment().run(str(first), str(second), str(attachment_path))

    assert name == "notas (2).txt"
    assert sorted(a.name for a in ListAttachments().run(str(second))) == ["notas (2).txt", "notas.txt"]
