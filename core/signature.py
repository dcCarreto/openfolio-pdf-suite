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

import contextlib
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
from pyhanko.sign.diff_analysis import ModificationLevel
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.status import SignatureCoverageLevel

from .base import PDFOperation, atomic_output, open_reader, require_valid_page_index
from .geometry import PageGeometry, intersect_rects

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
_FIELD_NAME = "OpenFolioSignature"
_STAMP_GAP = 6


def _unique_field_name(reader) -> str:
    """Nome de campo ainda não usado: num documento já assinado pelo app, a segunda
    assinatura (o contratado depois do contratante, por exemplo) ganha um campo próprio."""
    existing = set(reader.get_fields() or {})
    name, counter = _FIELD_NAME, 2
    while name in existing:
        name = f"{_FIELD_NAME}{counter}"
        counter += 1
    return name


def _stamp_box(page, position: str) -> tuple[float, float, float, float]:
    """Retângulo do selo no espaço do usuário: no canto pedido da página como ela aparece
    na tela e, se já houver selos de assinatura ali, empilhado ao lado deles (para cima
    nas posições de baixo, para baixo nas de cima) em vez de por cima."""
    geometry = PageGeometry.from_pypdf_page(page)
    occupied = []
    for ref in page.get("/Annots", []):
        annotation = ref.get_object()
        if annotation.get("/FT") == "/Sig" or annotation.get("/Parent", {}).get("/FT") == "/Sig":
            occupied.append(geometry.user_rect_to_visual(tuple(float(v) for v in annotation["/Rect"])))

    left, bottom, right, top = _POSITIONS[position](geometry.width, geometry.height)
    step = (_STAMP_HEIGHT + _STAMP_GAP) * (1 if position.startswith("bottom") else -1)
    for _attempt in range(int(geometry.height // (_STAMP_HEIGHT + _STAMP_GAP)) + 1):
        if not any(intersect_rects((left, bottom, right, top), other) for other in occupied):
            break
        bottom, top = bottom + step, top + step
    return geometry.visual_rect_to_user((left, bottom, right, top))


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
    """Assina um PDF: selo visível + assinatura criptográfica (CMS/PKCS#7).

    O arquivo assinado é gravado como atualização incremental do original (o que preserva
    assinaturas anteriores) e só ocupa o lugar do destino quando a assinatura terminou.
    """

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
            box = _stamp_box(reader.pages[page_index], position)
            field_name = _unique_field_name(reader)
            stamp_style = stamp.TextStampStyle(
                stamp_text="Assinado digitalmente por %(signer)s\n%(ts)s"
            )
            meta = signers.PdfSignatureMetadata(field_name=field_name)
            field_spec = fields.SigFieldSpec(field_name, on_page=page_index, box=box)
            pdf_signer = signers.PdfSigner(
                meta, signer=signer, stamp_style=stamp_style, new_field_spec=field_spec
            )

            with open(input_path, "rb") as inf, atomic_output(output_path) as temp_path:
                writer = IncrementalPdfFileWriter(inf)
                with open(temp_path, "wb") as outf:
                    pdf_signer.sign_pdf(
                        writer, output=outf, appearance_text_params={"signer": signer_name}
                    )


VERDICT_VALID = "valid"
VERDICT_WARNING = "warning"
VERDICT_INVALID = "invalid"

_COVERAGE_NAMES = {
    SignatureCoverageLevel.ENTIRE_FILE: "entire_file",
    SignatureCoverageLevel.ENTIRE_REVISION: "entire_revision",
    SignatureCoverageLevel.CONTIGUOUS_BLOCK_FROM_START: "partial",
    SignatureCoverageLevel.UNCLEAR: "unclear",
}
_MODIFICATION_NAMES = {
    ModificationLevel.NONE: "none",
    ModificationLevel.LTA_UPDATES: "lta_updates",
    ModificationLevel.FORM_FILLING: "form_filling",
    ModificationLevel.ANNOTATIONS: "annotations",
    ModificationLevel.OTHER: "other",
}


@dataclass
class SignatureInfo:
    """Resultado da verificação de uma assinatura.

    `intact` sozinho não basta para dizer que o documento não mudou: ele só garante que o
    trecho assinado (a revisão em que a assinatura foi feita) não foi alterado. Quem
    acrescenta uma atualização incremental depois da assinatura muda o que o leitor mostra
    sem tocar no trecho assinado — por isso `coverage`, `modification` e `docmdp_ok` entram
    no veredito (`verdict`).
    """

    field_name: str
    signer_name: str
    signing_time: str
    intact: bool
    valid: bool = False  # a assinatura confere criptograficamente com o certificado
    trusted: bool = False  # o certificado foi validado até uma autoridade confiável do sistema
    self_signed: bool = False
    issuer_name: str = ""
    cert_valid_from: str = ""
    cert_valid_until: str = ""
    coverage: str = "unclear"  # "entire_file" | "entire_revision" | "partial" | "unclear"
    modification: str = "unknown"  # "none" | "lta_updates" | "form_filling" | "annotations" | "other" | "unknown"
    docmdp_ok: bool | None = None
    revisions_after: int = 0  # revisões (atualizações incrementais) gravadas depois desta assinatura
    error: str = ""

    @property
    def verdict(self) -> str:
        """`VERDICT_VALID`, `VERDICT_WARNING` (válida, mas com ressalvas) ou `VERDICT_INVALID`."""
        if self.error or not self.intact or not self.valid:
            return VERDICT_INVALID
        if self.coverage not in ("entire_file", "entire_revision"):
            return VERDICT_INVALID
        if self.modification == "other" or self.docmdp_ok is False:
            return VERDICT_INVALID
        if not self.trusted or self.coverage != "entire_file" or self.modification == "unknown":
            return VERDICT_WARNING
        return VERDICT_VALID


def _common_name(name) -> str:
    native = name.native
    return str(native.get("common_name") or "") or name.human_friendly


class DescribeSignatures(PDFOperation):
    """Lista as assinaturas de um PDF com o resultado completo da verificação: integridade
    do trecho assinado, validade criptográfica, alterações feitas depois da assinatura e
    confiança no certificado.

    A confiança é verificada contra as autoridades certificadoras do sistema operacional,
    sem acessar a rede (o pyhanko não baixa listas de revogação por padrão). Certificados
    autoassinados — como o de teste gerado pelo app — nunca são considerados confiáveis.
    """

    def run(self, input_path: str) -> list[SignatureInfo]:
        with _quiet_pyhanko_logs():
            results = []
            with open(input_path, "rb") as f:
                reader = PdfFileReader(f)
                total_revisions = reader.xrefs.total_revisions
                for embedded in reader.embedded_signatures:
                    results.append(_describe(embedded, total_revisions))
            return results


# A validação da cadeia de confiança registra, em vários loggers internos do pyhanko, um erro
# esperado sempre que o certificado não chega a uma autoridade confiável (o caso do
# certificado de teste). Só esses loggers são silenciados, e só durante a checagem: antes o
# logging do processo inteiro era desligado, o que escondia erros de outras threads.
_PYHANKO_LOGGERS = ("pyhanko", "pyhanko_certvalidator")


@contextlib.contextmanager
def _quiet_pyhanko_logs():
    loggers = [logging.getLogger(name) for name in _PYHANKO_LOGGERS]
    previous = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        for logger, level in zip(loggers, previous):
            logger.setLevel(level)


def _describe(embedded, total_revisions: int) -> SignatureInfo:
    field_name = str(embedded.field_name or "")
    try:
        status = validate_pdf_signature(embedded)
    except Exception as exc:
        return SignatureInfo(
            field_name=field_name, signer_name="", signing_time="", intact=False, error=str(exc)
        )

    cert = status.signing_cert
    validity = cert["tbs_certificate"]["validity"]
    modification = status.modification_level
    return SignatureInfo(
        field_name=field_name,
        signer_name=_common_name(cert.subject),
        signing_time=str(status.signer_reported_dt) if status.signer_reported_dt else "",
        intact=bool(status.intact),
        valid=bool(status.valid),
        trusted=bool(status.trusted),
        self_signed=cert.self_signed != "no",
        issuer_name=_common_name(cert.issuer),
        cert_valid_from=validity["not_before"].native.date().isoformat(),
        cert_valid_until=validity["not_after"].native.date().isoformat(),
        coverage=_COVERAGE_NAMES.get(status.coverage, "unclear"),
        modification=_MODIFICATION_NAMES.get(modification, "unknown") if modification is not None else "unknown",
        docmdp_ok=status.docmdp_ok,
        revisions_after=max(0, total_revisions - 1 - embedded.signed_revision),
    )
