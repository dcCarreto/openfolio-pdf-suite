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
