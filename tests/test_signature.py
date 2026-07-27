"""Testes de core/signature.py: assinatura digital (CMS/PKCS#7) e verificação de integridade."""

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    load_pem_private_key,
    pkcs12,
)
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.signature import DescribeSignatures, SignDocument, generate_test_certificate


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
