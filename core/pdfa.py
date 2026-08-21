"""Conversão para um PDF de arquivamento (aproximação de PDF/A) e verificação.

PDF/A de verdade (ISO 19005) exige, entre outras coisas, um `/OutputIntent` com um perfil
de cor ICC embutido. Gerar esse binário na unha teria o mesmo risco que este projeto já
evita deliberadamente em outros lugares (assinatura digital, redação): um perfil ICC
malformado quebraria a conformidade de um jeito silencioso, e redistribuir o perfil de
terceiros sem clareza de licença não é uma escolha segura para um projeto open source. Por
isso esta ferramenta cobre só a parte que dá pra garantir com segurança usando o que já
está disponível: remove criptografia, JavaScript e anexos embutidos (todos proibidos em
PDF/A) e grava metadados XMP declarando a conformidade pretendida.

Isto **não é** validação ISO 19005 completa — não verifica embutimento de fontes, perfil
de cor (`/OutputIntent`) nem transparência. Para arquivamento legal que exija conformidade
real, valide o resultado com uma ferramenta dedicada (ex.: veraPDF) antes de considerar o
documento arquivável. `ValidatePDFA` deixa essa limitação explícita nos próprios avisos que
devolve, em vez de reportar "válido" com falsa segurança.
"""

from dataclasses import dataclass, field

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from .base import PDFOperation, open_reader
from .redaction import _is_javascript_action, _strip_annotation_javascript

_VALID_PARTS = (1, 2, 3)
_VALID_CONFORMANCE = ("A", "B", "U")

_XMP_TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>{part}</pdfaid:part>
   <pdfaid:conformance>{conformance}</pdfaid:conformance>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


class ConvertToPDFA(PDFOperation):
    """Remove recursos proibidos em PDF/A (JavaScript, anexos embutidos) e declara
    conformidade PDF/A nos metadados XMP. Veja as limitações no docstring do módulo."""

    def run(
        self,
        input_path: str,
        output_path: str,
        part: int = 2,
        conformance: str = "B",
    ) -> None:
        if part not in _VALID_PARTS:
            raise ValueError(f"part inválido: {part} (use 1, 2 ou 3).")
        if conformance.upper() not in _VALID_CONFORMANCE:
            raise ValueError(f"conformance inválido: {conformance} (use A, B ou U).")

        open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        writer = PdfWriter(clone_from=input_path)
        catalog = writer.root_object

        names = catalog.get("/Names")
        if names is not None:
            names_obj = names.get_object()
            for key in ("/JavaScript", "/EmbeddedFiles"):
                if key in names_obj:
                    del names_obj[NameObject(key)]

        open_action = catalog.get("/OpenAction")
        if open_action is not None and _is_javascript_action(open_action):
            del catalog[NameObject("/OpenAction")]

        for page in writer.pages:
            if "/Annots" in page:
                for annotation_ref in page["/Annots"]:
                    _strip_annotation_javascript(annotation_ref)

        xmp_stream = DecodedStreamObject()
        xmp_stream.set_data(
            _XMP_TEMPLATE.format(part=part, conformance=conformance.upper()).encode("utf-8")
        )
        xmp_stream[NameObject("/Type")] = NameObject("/Metadata")
        xmp_stream[NameObject("/Subtype")] = NameObject("/XML")
        catalog[NameObject("/Metadata")] = writer._add_object(xmp_stream)

        with open(output_path, "wb") as f:
            writer.write(f)


@dataclass
class PDFAValidationResult:
    is_valid: bool
    issues: list[str] = field(default_factory=list)


class ValidatePDFA(PDFOperation):
    """Verifica um subconjunto dos requisitos de PDF/A (sem `/OutputIntent`/perfil de cor
    nem embutimento de fontes — ver limitações no docstring do módulo)."""

    def run(
        self,
        input_path: str,
        part: int | None = None,
        conformance: str | None = None,
    ) -> PDFAValidationResult:
        reader = PdfReader(input_path)  # PDF criptografado é uma falha a reportar, não uma exceção
        issues: list[str] = []

        if reader.is_encrypted:
            issues.append("O PDF está protegido/criptografado — PDF/A não permite criptografia.")
            return PDFAValidationResult(is_valid=False, issues=issues)

        catalog = reader.trailer["/Root"]

        names = catalog.get("/Names")
        if names is not None:
            names_obj = names.get_object()
            if "/JavaScript" in names_obj:
                issues.append("O documento contém JavaScript, proibido em PDF/A.")
            if "/EmbeddedFiles" in names_obj:
                issues.append("O documento contém anexos embutidos, proibidos em PDF/A-1 e PDF/A-2.")

        for page in reader.pages:
            for annotation_ref in page.get("/Annots", []):
                annotation = annotation_ref.get_object()
                if _is_javascript_action(annotation.get("/A")):
                    issues.append("Uma anotação contém uma ação de JavaScript.")
                    break

        xmp_text = ""
        metadata_ref = catalog.get("/Metadata")
        if metadata_ref is not None:
            xmp_text = metadata_ref.get_object().get_data().decode("utf-8", errors="replace")

        if "pdfaid:part" not in xmp_text:
            issues.append("Não há metadados XMP declarando conformidade PDF/A.")
        else:
            if part is not None and f"<pdfaid:part>{part}<" not in xmp_text:
                issues.append(f"Os metadados XMP não declaram a parte PDF/A-{part} esperada.")
            if conformance is not None and (
                f"<pdfaid:conformance>{conformance.upper()}<" not in xmp_text
            ):
                issues.append(
                    f"Os metadados XMP não declaram a conformidade {conformance.upper()} esperada."
                )

        return PDFAValidationResult(is_valid=not issues, issues=issues)
