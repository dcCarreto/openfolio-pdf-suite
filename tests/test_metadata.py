import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.metadata import ReadMetadata, SetMetadata


def test_set_and_read_metadata(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "out.pdf"

    SetMetadata().run(
        str(pdf_path),
        str(output_path),
        title="Meu Documento",
        author="Autor Teste",
        subject="Assunto",
        keywords="pdf,teste",
    )

    metadata = ReadMetadata().run(str(output_path))
    assert metadata["title"] == "Meu Documento"
    assert metadata["author"] == "Autor Teste"
    assert metadata["subject"] == "Assunto"
    assert metadata["keywords"] == "pdf,teste"


def test_read_metadata_on_document_without_metadata(make_pdf):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])

    metadata = ReadMetadata().run(str(pdf_path))

    assert {key: metadata[key] for key in ("title", "author", "subject", "keywords", "creator")} == {
        "title": "",
        "author": "",
        "subject": "",
        "keywords": "",
        "creator": "",
    }
    assert metadata["created"] is None and metadata["modified"] is None


def test_set_metadata_preserves_omitted_fields(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    first_pass = tmp_path / "first.pdf"
    second_pass = tmp_path / "second.pdf"

    SetMetadata().run(
        str(pdf_path),
        str(first_pass),
        title="Título original",
        author="Autor original",
        subject="Assunto original",
        keywords="original",
    )

    # Só o título é informado na segunda chamada; os demais campos devem
    # permanecer com o valor gravado na primeira passada, não virar "".
    SetMetadata().run(str(first_pass), str(second_pass), title="Título novo")

    metadata = ReadMetadata().run(str(second_pass))
    assert metadata["title"] == "Título novo"
    assert metadata["author"] == "Autor original"
    assert metadata["subject"] == "Assunto original"
    assert metadata["keywords"] == "original"


def test_set_metadata_with_explicit_empty_string_clears_field(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    first_pass = tmp_path / "first.pdf"
    second_pass = tmp_path / "second.pdf"

    SetMetadata().run(str(pdf_path), str(first_pass), title="Título original")
    SetMetadata().run(str(first_pass), str(second_pass), title="")

    metadata = ReadMetadata().run(str(second_pass))
    assert metadata["title"] == ""


def test_read_metadata_rejects_encrypted_input(make_encrypted_pdf):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ReadMetadata().run(str(encrypted_path))


def test_set_metadata_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        SetMetadata().run(str(encrypted_path), str(tmp_path / "out.pdf"), title="X")


def test_creator_producer_and_dates(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    output_path = tmp_path / "out.pdf"

    SetMetadata().run(str(pdf_path), str(output_path), creator="Writer", producer="Gerador X")

    metadata = ReadMetadata().run(str(output_path))
    assert metadata["creator"] == "Writer" and metadata["producer"] == "Gerador X"
    assert metadata["modified"] is not None  # a data de modificação passa a ser a de agora


def test_xmp_receives_creator_tool_and_producer(make_pdf, tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.xmp import XmpInformation

    pdf_path = make_pdf("doc.pdf", [(200, 200)])
    writer = PdfWriter(clone_from=str(pdf_path))
    writer.xmp_metadata = XmpInformation.create()
    writer.write(str(pdf_path))
    output_path = tmp_path / "out.pdf"

    SetMetadata().run(str(pdf_path), str(output_path), creator="Writer", producer="Gerador X")

    xmp = PdfReader(str(output_path)).xmp_metadata
    assert xmp.xmp_creator_tool == "Writer" and xmp.pdf_producer == "Gerador X"


_XMP = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:rights><rdf:Alt><rdf:li xml:lang="x-default">Uso interno — São Paulo</rdf:li></rdf:Alt></dc:rights>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def test_xmp_is_written_whole_and_uncompressed(make_pdf, tmp_path):
    from core.metadata import SetXMP, read_xmp

    source, output, cleared = make_pdf("doc.pdf", [(200, 200)]), tmp_path / "xmp.pdf", tmp_path / "sem.pdf"
    assert read_xmp(str(source)) == ""

    SetXMP().run(str(source), str(output), _XMP)

    assert read_xmp(str(output)) == _XMP
    assert "Uso interno — São Paulo".encode() in output.read_bytes()  # sem compressão
    reader = PdfReader(str(output))
    assert reader.xmp_metadata.dc_rights == {"x-default": "Uso interno — São Paulo"}
    SetXMP().run(str(output), str(cleared), "  ")
    assert "/Metadata" not in PdfReader(str(cleared)).root_object


@pytest.mark.parametrize("xmp, message", [("<x:xmpmeta", "não é um XML válido"), ("<html/>", "na raiz")])
def test_bad_xmp_is_refused(make_pdf, tmp_path, xmp, message):
    from core.metadata import SetXMP

    with pytest.raises(ValueError, match=message):
        SetXMP().run(str(make_pdf("doc.pdf", [(200, 200)])), str(tmp_path / "o.pdf"), xmp)
