"""Testes de core/links.py: anotações de link (hyperlink)."""

import pytest

from core.base import EncryptedPDFError
from core.links import AddLink, ListLinks, RemoveLink


def test_add_link_with_url(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    AddLink().run(
        str(pdf_path), str(output_path), page_number=0, left=10, bottom=10, right=100, top=30,
        url="https://example.com",
    )

    links = ListLinks().run(str(output_path))
    assert len(links) == 1
    assert links[0].target == "https://example.com"


def test_add_link_with_target_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300), (300, 300)])
    output_path = tmp_path / "out.pdf"

    AddLink().run(
        str(pdf_path), str(output_path), page_number=0, left=10, bottom=10, right=100, top=30,
        target_page=1,
    )

    links = ListLinks().run(str(output_path))
    assert len(links) == 1
    assert links[0].target == "página 2"  # antes só dizia "destino interno"


def test_add_link_requires_exactly_one_target(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        AddLink().run(str(pdf_path), str(tmp_path / "out.pdf"), page_number=0, left=0, bottom=0, right=10, top=10)
    with pytest.raises(ValueError):
        AddLink().run(
            str(pdf_path), str(tmp_path / "out.pdf"), page_number=0, left=0, bottom=0, right=10, top=10,
            url="https://example.com", target_page=0,
        )


def test_add_link_rejects_invalid_target_page(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        AddLink().run(
            str(pdf_path), str(tmp_path / "out.pdf"), page_number=0, left=0, bottom=0, right=10, top=10,
            target_page=5,
        )


def test_add_link_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        AddLink().run(
            str(encrypted_path), str(tmp_path / "out.pdf"), page_number=0, left=0, bottom=0, right=10, top=10,
            url="https://example.com",
        )


def test_list_links_empty_when_no_links(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    assert ListLinks().run(str(pdf_path)) == []


def test_remove_link(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    with_links = tmp_path / "with_links.pdf"
    AddLink().run(
        str(pdf_path), str(with_links), page_number=0, left=10, bottom=10, right=50, top=30,
        url="https://a.example.com",
    )
    with_two_links = tmp_path / "with_two_links.pdf"
    AddLink().run(
        str(with_links), str(with_two_links), page_number=0, left=60, bottom=10, right=100, top=30,
        url="https://b.example.com",
    )

    output_path = tmp_path / "out.pdf"
    RemoveLink().run(str(with_two_links), str(output_path), page_number=0, link_index=0)

    links = ListLinks().run(str(output_path))
    assert len(links) == 1
    assert links[0].target == "https://b.example.com"


def test_remove_link_rejects_invalid_index(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    with_link = tmp_path / "with_link.pdf"
    AddLink().run(
        str(pdf_path), str(with_link), page_number=0, left=10, bottom=10, right=50, top=30,
        url="https://example.com",
    )

    with pytest.raises(ValueError):
        RemoveLink().run(str(with_link), str(tmp_path / "out.pdf"), page_number=0, link_index=3)


def test_remove_link_rejects_page_without_links(make_pdf, tmp_path):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])

    with pytest.raises(ValueError):
        RemoveLink().run(str(pdf_path), str(tmp_path / "out.pdf"), page_number=0, link_index=0)


def test_remove_link_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        RemoveLink().run(str(encrypted_path), str(tmp_path / "out.pdf"), page_number=0, link_index=0)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("exemplo.com", "https://exemplo.com"),
        ("www.exemplo.com/a?b=1", "https://www.exemplo.com/a?b=1"),
        ("ana@exemplo.com", "mailto:ana@exemplo.com"),
        ("http://exemplo.com", "http://exemplo.com"),
        ("mailto:ana@exemplo.com", "mailto:ana@exemplo.com"),
    ],
)
def test_url_without_scheme_is_completed(make_pdf, tmp_path, typed, expected):
    pdf_path = make_pdf("doc.pdf", [(300, 300)])
    output_path = tmp_path / "out.pdf"

    AddLink().run(str(pdf_path), str(output_path), page_number=0, left=10, bottom=10, right=100, top=30, url=typed)

    assert ListLinks().run(str(output_path))[0].target == expected
