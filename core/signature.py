"""Assinatura digital de PDFs: selo visível sobre a página + assinatura criptográfica de
verdade (CMS/PKCS#7, conforme ISO 32000), com verificação de integridade.

Nem pypdf nem nenhuma outra ferramenta já usada neste projeto sabem assinar PDFs — o
próprio código do pypdf registra que "Signature forms not implemented yet". Assinatura
digital de PDF é uma cirurgia de bytes delicada (estrutura /ByteRange + /Contents), a mesma
categoria de risco de "parecer certo mas estar sutilmente errado" que já levou a preferir
motores prontos em vez de reimplementar algo sensível a erros sutis (mesmo princípio do
OCR com o Tesseract). Por isso usamos `pyhanko`, uma biblioteca madura mantida
especificamente para assinar/validar PDFs.

Dois jeitos de obter o certificado usado para assinar:
- Um arquivo .pfx/.p12 de verdade do usuário (ex.: certificado ICP-Brasil) — assinatura com
  identidade real.
- Um certificado autoassinado gerado na hora pelo próprio app — sem validade jurídica,
  para testar o fluxo ou uso pessoal/interno.
"""

import datetime
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature

from .base import PDFOperation, open_reader, require_valid_page_index

_STAMP_WIDTH = 175
_STAMP_HEIGHT = 50
_MARGIN = 15

_POSITIONS = {
    "bottom-right": lambda w, h: (w - _MARGIN - _STAMP_WIDTH, _MARGIN, w - _MARGIN, _MARGIN + _STAMP_HEIGHT),
    "bottom-left": lambda w, h: (_MARGIN, _MARGIN, _MARGIN + _STAMP_WIDTH, _MARGIN + _STAMP_HEIGHT),
    "top-right": lambda w, h: (
        w - _MARGIN - _STAMP_WIDTH,
        h - _MARGIN - _STAMP_HEIGHT,
        w - _MARGIN,
        h - _MARGIN,
    ),
    "top-left": lambda w, h: (_MARGIN, h - _MARGIN - _STAMP_HEIGHT, _MARGIN + _STAMP_WIDTH, h - _MARGIN),
}


def generate_test_certificate(common_name: str, email: str) -> tuple[bytes, bytes]:
    """Gera um par chave/certificado autoassinado, só para teste/uso local (sem validade jurídica)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 3))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


def _load_pfx_signer(pfx_path: str, password: str | None):
    passphrase = password.encode("utf-8") if password else None
    signer = signers.SimpleSigner.load_pkcs12(pfx_path, passphrase=passphrase)
    if signer is None:
        raise ValueError(
            "Não foi possível carregar o certificado .pfx (senha incorreta ou arquivo inválido)."
        )
    return signer


def _load_test_signer(common_name: str, email: str, tmp_dir: str):
    key_pem, cert_pem = generate_test_certificate(common_name, email)
    key_path = Path(tmp_dir) / "signer_key.pem"
    cert_path = Path(tmp_dir) / "signer_cert.pem"
    key_path.write_bytes(key_pem)
    cert_path.write_bytes(cert_pem)
    signer = signers.SimpleSigner.load(str(key_path), str(cert_path))
    if signer is None:
        raise ValueError("Falha ao gerar o certificado de teste.")
    return signer


class SignDocument(PDFOperation):
    """Assina um PDF: selo visível + assinatura criptográfica (CMS/PKCS#7)."""

    def run(
        self,
        input_path: str,
        output_path: str,
        *,
        signer_name: str,
        page_index: int = 0,
        position: str = "bottom-right",
        pfx_path: str | None = None,
        pfx_password: str | None = None,
        test_common_name: str | None = None,
        test_email: str | None = None,
    ) -> None:
        if position not in _POSITIONS:
            raise ValueError(f"Posição inválida: {position}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            if pfx_path:
                signer = _load_pfx_signer(pfx_path, pfx_password)
            elif test_common_name:
                signer = _load_test_signer(test_common_name, test_email or "", tmp_dir)
            else:
                raise ValueError(
                    "Informe um certificado .pfx ou os dados para gerar um certificado de teste."
                )

            reader = open_reader(input_path)
            require_valid_page_index(len(reader.pages), page_index)
            page = reader.pages[page_index]
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            box = _POSITIONS[position](width, height)

            field_name = "OpenFolioSignature"
            stamp_style = stamp.TextStampStyle(
                stamp_text="Assinado digitalmente por %(signer)s\n%(ts)s"
            )
            meta = signers.PdfSignatureMetadata(field_name=field_name)
            field_spec = fields.SigFieldSpec(field_name, on_page=page_index, box=box)
            pdf_signer = signers.PdfSigner(
                meta, signer=signer, stamp_style=stamp_style, new_field_spec=field_spec
            )

            with open(input_path, "rb") as inf:
                writer = IncrementalPdfFileWriter(inf)
                with open(output_path, "wb") as outf:
                    pdf_signer.sign_pdf(
                        writer, output=outf, appearance_text_params={"signer": signer_name}
                    )


@dataclass
class SignatureInfo:
    field_name: str
    signer_name: str
    signing_time: str
    intact: bool


class DescribeSignatures(PDFOperation):
    """Lista as assinaturas de um PDF com o resultado da verificação de integridade
    (não valida a cadeia de confiança do certificado, só a identidade declarada e se o
    documento foi alterado depois de assinado)."""

    def run(self, input_path: str) -> list[SignatureInfo]:
        # A validação de cadeia de confiança (fora do escopo aqui) registra, em vários
        # loggers internos do pyhanko, um erro esperado sempre que o certificado não tem
        # uma autoridade confiável configurada (o nosso caso, de propósito). Silenciamos o
        # logging inteiro durante a checagem para isso não parecer um bug no console.
        previous_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            results = []
            with open(input_path, "rb") as f:
                reader = PdfFileReader(f)
                for embedded in reader.embedded_signatures:
                    status = validate_pdf_signature(embedded)
                    signing_time = (
                        str(status.signer_reported_dt) if status.signer_reported_dt else ""
                    )
                    results.append(
                        SignatureInfo(
                            field_name=embedded.field_name,
                            signer_name=status.signing_cert.subject.human_friendly,
                            signing_time=signing_time,
                            intact=bool(status.intact),
                        )
                    )
            return results
        finally:
            logging.disable(previous_level)
