import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.bookmarks import AddBookmarks


def test_add_bookmarks(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(200, 200), (200, 200), (200, 200)])
    output_path = tmp_path / "bookmarked.pdf"

    AddBookmarks().run(
        str(pdf_path),
        str(output_path),
        bookmarks=[("Capítulo 1", 0), ("Capítulo 2", 2)],
    )

    reader = PdfReader(str(output_path))
    outline = reader.outline
    assert len(outline) == 2
    assert outline[0].title == "Capítulo 1"
    assert outline[1].title == "Capítulo 2"


def test_add_bookmarks_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddBookmarks().run(str(encrypted_path), str(tmp_path / "out.pdf"), bookmarks=[("Cap", 0)])
