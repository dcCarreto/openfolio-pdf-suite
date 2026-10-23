"""Assinatura digital de PDFs: selo visível sobre a página + assinatura criptográfica de
verdade (CMS/PKCS#7, conforme ISO 32000), com verificação de integridade.

Nem pypdf nem nenhuma outra ferramenta já usada neste projeto sabem assinar PDFs — o
próprio código do pypdf registra que "Signature forms not implemented yet". Assinatura
digital de PDF é uma cirurgia de bytes delicada (estrutura /ByteRange + /Contents), a mesma
categoria de risco de "parecer certo mas estar sutilmente errado" que já levou a preferir
motores prontos em vez de reimplementar algo sensível a erros sutis (mesmo princípio do
OCR com o Tesseract). Por isso usamos `pyhanko`, uma biblioteca madura mantida
especificamente para assinar/validar PDFs.

O nome no selo é o do certificado (um texto livre podia contradizê-lo). Opcionais: motivo,
local e contato (gravados na assinatura e mostrados no selo), carimbo de tempo de um servidor
TSA (a data passa a ser atestada por terceiros, não pelo relógio de quem assina; o servidor
recebe só o resumo criptográfico do documento), o formato PAdES (ETSI.CAdES.detached, o
padrão europeu, em vez do adbe.pkcs7.detached) e uma imagem, como a assinatura escaneada,
no selo.

Dois jeitos de obter o certificado usado para assinar:
- Um arquivo .pfx/.p12 de verdade do usuário (ex.: certificado ICP-Brasil) — assinatura com
  identidade real.
- Um certificado autoassinado gerado na hora pelo próprio app — sem validade jurídica,
  para testar o fluxo ou uso pessoal/interno.
"""

import asyncio
import contextlib
import datetime
import logging
from dataclasses import dataclass

from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from oscrypto import trust_list
from pyhanko import stamp
from pyhanko.pdf_utils import images, layout
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.diff_analysis import ModificationLevel
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.status import SignatureCoverageLevel
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore

from .base import atomic_output, open_reader, require_valid_page_index
from .geometry import PageGeometry, intersect_rects, normalize_rect
from .messages import Message

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
            occupied.append(geometry.user_rect_to_visual(normalize_rect(annotation["/Rect"])))

    left, bottom, right, top = _POSITIONS[position](geometry.width, geometry.height)
    step = (_STAMP_HEIGHT + _STAMP_GAP) * (1 if position.startswith("bottom") else -1)
    for _attempt in range(int(geometry.height // (_STAMP_HEIGHT + _STAMP_GAP)) + 1):
        if not any(intersect_rects((left, bottom, right, top), other) for other in occupied):
            break
        bottom, top = bottom + step, top + step
    return geometry.visual_rect_to_user((left, bottom, right, top))


def generate_test_certificate(common_name: str, email: str) -> tuple[bytes, bytes]:
    """Gera um par chave/certificado autoassinado, só para teste/uso local (sem validade
    jurídica), em PEM."""
    key, cert = _new_test_certificate(common_name, email)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key_pem, cert.public_bytes(serialization.Encoding.PEM)


def _new_test_certificate(common_name: str, email: str):
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
    return key, cert


def _load_pfx_signer(pfx_path: str, password: str | None):
    passphrase = password.encode("utf-8") if password else None
    signer = signers.SimpleSigner.load_pkcs12(pfx_path, passphrase=passphrase)
    if signer is None:
        raise ValueError(
            "Não foi possível carregar o certificado .pfx (senha incorreta ou arquivo inválido)."
        )
    return signer


@dataclass
class CertificateSummary:
    """Os dados de um certificado que importam antes de assinar com ele."""

    name: str
    issuer_name: str
    valid_from: str
    valid_until: str
    self_signed: bool
    expired: bool


def describe_certificate(pfx_path: str, password: str | None) -> CertificateSummary:
    """Abre o .pfx/.p12 (mesma senha da assinatura) e resume o certificado."""
    return _summary(_load_pfx_signer(pfx_path, password).signing_cert)


def _summary(cert) -> CertificateSummary:
    validity = cert["tbs_certificate"]["validity"]
    valid_until = validity["not_after"].native
    return CertificateSummary(
        name=_common_name(cert.subject),
        issuer_name=_common_name(cert.issuer),
        valid_from=validity["not_before"].native.date().isoformat(),
        valid_until=valid_until.date().isoformat(),
        self_signed=cert.self_signed != "no",
        expired=valid_until < datetime.datetime.now(datetime.timezone.utc),
    )


def _timestamper(url: str):
    """O servidor de carimbo de tempo (isolado para os testes, que não usam a rede)."""
    return timestamps.HTTPTimeStamper(url, timeout=20)


class _OpaqueStamp(stamp.TextStamp):
    """O selo do pyhanko é transparente: numa capa escura ou sobre um logotipo o texto preto
    some. Um fundo branco o deixa legível em qualquer página."""

    def render(self):
        content = super().render()  # só depois dele a caixa tem tamanho
        return b"q 1 g 0 0 %g %g re f Q " % (self.box.width, self.box.height) + content


class _StampStyle(stamp.TextStampStyle):
    def create_stamp(self, writer, box, text_params):
        return _OpaqueStamp(writer=writer, style=self, box=box, text_params=text_params)


def _stamp_style(lines: list[str], image_path: str | None, box) -> stamp.TextStampStyle:
    # O pyhanko usa "%(nome)s" no texto: um "%" digitado pelo usuário vira "%%".
    text = "\n".join(lines)
    if image_path is None:
        return _StampStyle(stamp_text=text)
    # A imagem na metade esquerda do selo, o texto na direita.
    half = int((box[2] - box[0]) / 2)
    try:
        image = images.PdfImage(image_path)
    except Exception as error:  # o Pillow avisa de vários jeitos que não é uma imagem
        raise ValueError(Message("Não foi possível ler a imagem do selo: {error}", error=str(error))) from error
    return _StampStyle(
        stamp_text=text,
        background=image,
        background_opacity=1,
        background_layout=layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MIN,
            y_align=layout.AxisAlignment.ALIGN_MID,
            margins=layout.Margins(left=4, right=half, top=4, bottom=4),
        ),
        inner_content_layout=layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MIN,
            y_align=layout.AxisAlignment.ALIGN_MID,
            margins=layout.Margins(left=half + 2, right=4),
        ),
    )


def _test_signer(common_name: str, email: str) -> signers.SimpleSigner:
    """Quem assina com um certificado de teste gerado agora, só na memória: a chave privada
    nunca vai para o disco (antes ia para um diretório temporário, para o pyhanko ler)."""
    key, cert = _new_test_certificate(common_name, email)
    signing_cert = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    signing_key = asn1_keys.PrivateKeyInfo.load(
        key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return signers.SimpleSigner(
        signing_cert=signing_cert,
        signing_key=signing_key,
        cert_registry=SimpleCertificateStore.from_certs([signing_cert]),
    )


class SignDocument:
    """Assina um PDF: selo visível + assinatura criptográfica (CMS/PKCS#7).

    O arquivo assinado é gravado como atualização incremental do original (o que preserva
    assinaturas anteriores) e só ocupa o lugar do destino quando a assinatura terminou.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        *,
        signer_name: str | None = None,
        page_index: int = 0,
        position: str = "bottom-right",
        pfx_path: str | None = None,
        pfx_password: str | None = None,
        test_common_name: str | None = None,
        test_email: str | None = None,
        box: tuple[float, float, float, float] | None = None,
        reason: str = "",
        location: str = "",
        contact: str = "",
        timestamp_url: str = "",
        pades: bool = False,
        stamp_image: str | None = None,
    ) -> None:
        """`box` (left, bottom, right, top no espaço do usuário), se informado, é a área do
        selo marcada no visualizador e substitui `position`. `signer_name` vazio usa o nome
        do certificado."""
        if box is None and position not in _POSITIONS:
            raise ValueError(f"Posição inválida: {position}")
        if box is not None and (box[2] - box[0] < 20 or box[3] - box[1] < 10):
            raise ValueError("A área do selo é pequena demais: marque pelo menos 20 x 10 pontos.")

        if pfx_path:
            signer = _load_pfx_signer(pfx_path, pfx_password)
        elif test_common_name:
            signer = _test_signer(test_common_name, test_email or "")
        else:
            raise ValueError(
                "Informe um certificado .pfx ou os dados para gerar um certificado de teste."
            )
        certificate = _summary(signer.signing_cert)
        if certificate.expired:
            raise ValueError(
                Message(
                    "O certificado venceu em {date}: a assinatura não seria válida. Use um certificado em dia.",
                    date=certificate.valid_until,
                )
            )

        reader = open_reader(input_path)
        require_valid_page_index(len(reader.pages), page_index)
        if box is None:
            box = _stamp_box(reader.pages[page_index], position)
        field_name = _unique_field_name(reader)
        reason, location, contact = reason.strip(), location.strip(), contact.strip()
        lines = ["Assinado digitalmente por %(signer)s", "%(ts)s"]
        lines += [f"{label}: {value.replace('%', '%%')}" for label, value in (("Motivo", reason), ("Local", location)) if value]
        stamp_style = _stamp_style(lines, stamp_image, box)
        meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=reason or None,
            location=location or None,
            contact_info=contact or None,
            subfilter=fields.SigSeedSubFilter.PADES if pades else None,
        )
        # O pyhanko anota a caixa como inteiros, mas grava frações de ponto sem problema.
        field_spec = fields.SigFieldSpec(field_name, on_page=page_index, box=box)  # type: ignore[arg-type]
        pdf_signer = signers.PdfSigner(
            meta,
            signer=signer,
            stamp_style=stamp_style,
            new_field_spec=field_spec,
            timestamper=_timestamper(timestamp_url.strip()) if timestamp_url.strip() else None,
        )
        name = (signer_name or "").strip() or certificate.name

        with open(input_path, "rb") as inf, atomic_output(output_path) as temp_path:
            writer = IncrementalPdfFileWriter(inf)
            with open(temp_path, "wb") as outf:
                try:
                    pdf_signer.sign_pdf(writer, output=outf, appearance_text_params={"signer": name})
                except timestamps.TimestampRequestError as error:
                    raise ValueError(
                        Message(
                            "Não foi possível obter o carimbo de tempo de {url}: {error}",
                            url=timestamp_url.strip(),
                            error=str(error),
                        )
                    ) from error
                except (asyncio.CancelledError, asyncio.TimeoutError) as error:
                    # O tempo do servidor acabou: no Python 3.10 o aiohttp deixa escapar o
                    # cancelamento do asyncio (BaseException), sem texto, em vez do erro acima.
                    raise ValueError(
                        Message("O servidor de carimbo de tempo {url} não respondeu.", url=timestamp_url.strip())
                    ) from error


VERDICT_VALID = "valid"
VERDICT_WARNING = "warning"
VERDICT_INVALID = "invalid"

_COVERAGE_NAMES: dict[SignatureCoverageLevel | None, str] = {
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
    reason: str = ""
    location: str = ""
    contact: str = ""
    pades: bool = False  # formato ETSI.CAdES.detached
    timestamp: str = ""  # data atestada pelo servidor de carimbo de tempo, se houver
    timestamp_valid: bool | None = None  # o carimbo confere (None: sem carimbo)
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


class DescribeSignatures:
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


def _trust_roots() -> list:
    """Autoridades certificadoras do sistema: o repositório do Windows, as chaves do macOS ou o
    pacote de CAs da distribuição Linux. O pyhanko vai deixar de buscá-las sozinho."""
    return [cert for cert, _trust_oids, _reject_oids in trust_list.get_list()]


def _describe(embedded, total_revisions: int) -> SignatureInfo:
    field_name = str(embedded.field_name or "")
    try:
        status = validate_pdf_signature(embedded, ValidationContext(trust_roots=_trust_roots()))
    except Exception as exc:
        return SignatureInfo(
            field_name=field_name, signer_name="", signing_time="", intact=False, error=str(exc)
        )

    cert = status.signing_cert
    validity = cert["tbs_certificate"]["validity"]
    modification = status.modification_level
    sig_object = embedded.sig_object
    timestamp = status.timestamp_validity
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
        reason=str(sig_object.get("/Reason", "")),
        location=str(sig_object.get("/Location", "")),
        contact=str(sig_object.get("/ContactInfo", "")),
        pades=sig_object.get("/SubFilter") == "/ETSI.CAdES.detached",
        timestamp=str(timestamp.timestamp) if timestamp is not None else "",
        timestamp_valid=bool(timestamp.intact and timestamp.valid) if timestamp is not None else None,
    )
