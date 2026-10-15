"""Testes de core/signature.py: assinatura digital (CMS/PKCS#7) e verificação de integridade."""

import io

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    load_pem_private_key,
    pkcs12,
)
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.signature import (
    VERDICT_INVALID,
    VERDICT_WARNING,
    DescribeSignatures,
    SignDocument,
    generate_test_certificate,
)


def _make_pdf(path, text: str) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=(400, 300))
    canvas.setFont("Helvetica", 16)
    canvas.drawString(50, 200, text)
    canvas.showPage()
    canvas.save()


def test_generate_test_certificate_returns_pem_key_and_cert():
    key_pem, cert_pem = generate_test_certificate("Fulano de Tal", "fulano@example.com")

    assert key_pem.startswith(b"-----BEGIN")
    assert cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")


def test_sign_with_test_certificate_is_detected_and_intact(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_signed.pdf"
    _make_pdf(path_in, "Contrato de teste")

    SignDocument().run(
        str(path_in),
        str(path_out),
        signer_name="Fulano de Tal",
        page_index=0,
        position="bottom-right",
        test_common_name="Fulano de Tal",
        test_email="fulano@example.com",
    )

    signatures = DescribeSignatures().run(str(path_out))
    assert len(signatures) == 1
    assert signatures[0].intact is True
    assert "Fulano de Tal" in signatures[0].signer_name
    assert signatures[0].signing_time


def test_sign_with_pfx_certificate(tmp_path):
    key_pem, cert_pem = generate_test_certificate("Empresa Exemplo", "contato@empresa.example")
    key = load_pem_private_key(key_pem, password=None)
    cert = x509.load_pem_x509_certificate(cert_pem)
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"openfolio-test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(b"senha123"),
    )
    pfx_path = tmp_path / "cert.pfx"
    pfx_path.write_bytes(pfx_bytes)

    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_signed.pdf"
    _make_pdf(path_in, "Documento assinado com pfx")

    SignDocument().run(
        str(path_in),
        str(path_out),
        signer_name="Empresa Exemplo",
        pfx_path=str(pfx_path),
        pfx_password="senha123",
    )

    signatures = DescribeSignatures().run(str(path_out))
    assert len(signatures) == 1
    assert signatures[0].intact is True


def test_tampering_after_signing_breaks_integrity(tmp_path):
    path_in = tmp_path / "doc.pdf"
    path_out = tmp_path / "doc_signed.pdf"
    _make_pdf(path_in, "Documento que sera adulterado")

    SignDocument().run(
        str(path_in),
        str(path_out),
        signer_name="Fulano de Tal",
        test_common_name="Fulano de Tal",
        test_email="fulano@example.com",
    )

    data = bytearray(path_out.read_bytes())
    mid = len(data) // 3
    data[mid] = (data[mid] + 1) % 256
    path_tampered = tmp_path / "doc_tampered.pdf"
    path_tampered.write_bytes(bytes(data))

    signatures = DescribeSignatures().run(str(path_tampered))
    assert len(signatures) == 1
    assert signatures[0].intact is False


def test_describe_signatures_returns_empty_for_unsigned_pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path, "Documento sem assinatura")

    assert DescribeSignatures().run(str(path)) == []


def test_sign_requires_a_certificate_source(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in, "Sem certificado")

    with pytest.raises(ValueError):
        SignDocument().run(str(path_in), str(tmp_path / "out.pdf"), signer_name="Alguém")


def test_sign_rejects_out_of_range_page_index(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in, "Página única")

    with pytest.raises(ValueError):
        SignDocument().run(
            str(path_in),
            str(tmp_path / "out.pdf"),
            signer_name="Fulano de Tal",
            page_index=5,
            test_common_name="Fulano de Tal",
            test_email="fulano@example.com",
        )


def test_sign_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        SignDocument().run(
            str(encrypted_path),
            str(tmp_path / "out.pdf"),
            signer_name="Fulano de Tal",
            test_common_name="Fulano de Tal",
            test_email="fulano@example.com",
        )


def test_sign_rejects_invalid_position(tmp_path):
    path_in = tmp_path / "doc.pdf"
    _make_pdf(path_in, "Posicao invalida")

    with pytest.raises(ValueError):
        SignDocument().run(
            str(path_in),
            str(tmp_path / "out.pdf"),
            signer_name="Alguém",
            position="meio-do-nada",
            test_common_name="Alguém",
            test_email="a@example.com",
        )


def _signed_with_test_certificate(tmp_path, text: str = "Valor do contrato: R$ 1.000,00"):
    path_in = tmp_path / "contrato.pdf"
    path_out = tmp_path / "assinado.pdf"
    _make_pdf(path_in, text)
    SignDocument().run(
        str(path_in),
        str(path_out),
        signer_name="Fulano de Tal",
        test_common_name="Fulano de Tal",
        test_email="fulano@example.com",
    )
    return path_out


def test_untouched_signature_covers_the_whole_file_but_test_certificate_is_not_trusted(tmp_path):
    signed = _signed_with_test_certificate(tmp_path)

    (info,) = DescribeSignatures().run(str(signed))

    assert info.intact and info.valid
    assert info.coverage == "entire_file"
    assert info.modification == "none"
    assert info.revisions_after == 0
    assert info.signer_name == "Fulano de Tal"
    assert info.self_signed is True
    assert info.trusted is False
    assert info.cert_valid_from and info.cert_valid_until
    # Válida, mas com ressalva: um certificado autoassinado não prova a identidade de ninguém.
    assert info.verdict == VERDICT_WARNING


def test_content_added_by_incremental_update_after_signing_is_reported(tmp_path):
    # O trecho assinado continua intacto (`intact` é True), mas uma atualização incremental
    # muda o que o leitor mostra. Antes isso aparecia como "íntegro (não modificado)".
    signed = _signed_with_test_certificate(tmp_path)

    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(400, 300))
    canvas.drawString(50, 150, "ADENDO: valor alterado para R$ 900.000,00")
    canvas.save()
    buffer.seek(0)
    writer = PdfWriter(str(signed), incremental=True)
    writer.pages[0].merge_page(PdfReader(buffer).pages[0])
    tampered = tmp_path / "adulterado.pdf"
    writer.write(str(tampered))
    assert "900.000,00" in PdfReader(str(tampered)).pages[0].extract_text()

    (info,) = DescribeSignatures().run(str(tampered))

    assert info.intact is True
    assert info.coverage == "entire_revision"
    assert info.revisions_after == 1
    assert info.modification == "other"
    assert info.verdict == VERDICT_INVALID


def test_tampered_bytes_are_reported_as_invalid(tmp_path):
    signed = _signed_with_test_certificate(tmp_path, "Documento que sera adulterado")
    data = bytearray(signed.read_bytes())
    mid = len(data) // 3
    data[mid] = (data[mid] + 1) % 256
    tampered = tmp_path / "tampered.pdf"
    tampered.write_bytes(bytes(data))

    (info,) = DescribeSignatures().run(str(tampered))

    assert info.verdict == VERDICT_INVALID


def test_a_signed_document_can_be_signed_again_without_covering_the_first_stamp(tmp_path):
    # O nome de campo fixo impedia a segunda assinatura (contratante e contratado).
    signed = _signed_with_test_certificate(tmp_path)
    twice = tmp_path / "assinado_duas_vezes.pdf"

    SignDocument().run(
        str(signed),
        str(twice),
        signer_name="Ciclano",
        test_common_name="Ciclano",
        test_email="c@example.com",
    )

    first, second = DescribeSignatures().run(str(twice))
    assert first.field_name != second.field_name
    assert second.verdict == VERDICT_WARNING and second.coverage == "entire_file"
    # A primeira assinatura continua válida: a segunda só acrescentou uma revisão de assinatura.
    assert first.intact and first.modification in ("none", "lta_updates", "form_filling")

    widgets = [ref.get_object() for ref in PdfReader(str(twice)).pages[0]["/Annots"]]
    rects = [[float(v) for v in widget["/Rect"]] for widget in widgets]
    (a, b) = rects
    assert a[3] <= b[1] or b[3] <= a[1]  # empilhados, sem sobreposição


def test_stamp_goes_to_the_visual_corner_on_rotated_pages(make_text_pdf, tmp_path):
    from core.geometry import PageGeometry

    path_in = make_text_pdf("rot.pdf", [(80, 650, "contrato")], rotate=90)
    path_out = tmp_path / "assinado.pdf"
    SignDocument().run(
        str(path_in), str(path_out), signer_name="Fulano", test_common_name="Fulano",
        test_email="f@example.com", position="bottom-right",
    )

    page = PdfReader(str(path_out)).pages[0]
    widget = page["/Annots"][0].get_object()
    geometry = PageGeometry.from_pypdf_page(page)
    left, bottom, right, top = geometry.user_rect_to_visual(tuple(float(v) for v in widget["/Rect"]))
    assert right > geometry.width - 30 and bottom < 30  # canto inferior direito da tela
