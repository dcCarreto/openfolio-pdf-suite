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

    assert metadata == {"title": "", "author": "", "subject": "", "keywords": ""}


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
