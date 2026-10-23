"""Testes do relatório de verificação de assinatura (ui/pages/signature_page.py)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.signature import SignatureInfo
from ui.pages.signature_page import format_signature_info


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _info(**overrides) -> SignatureInfo:
    values = dict(
        field_name="OpenFolioSignature",
        signer_name="Fulano de Tal",
        signing_time="2026-10-15 14:11:18+00:00",
        intact=True,
        valid=True,
        trusted=False,
        self_signed=True,
        issuer_name="Fulano de Tal",
        cert_valid_from="2026-10-15",
        cert_valid_until="2029-10-14",
        coverage="entire_file",
        modification="none",
        docmdp_ok=True,
    )
    values.update(overrides)
    return SignatureInfo(**values)


def test_report_for_self_signed_untouched_signature():
    _app()
    text = format_signature_info(_info(), 1, 1)

    assert "Resultado: VÁLIDA, COM RESSALVAS" in text
    assert "Fulano de Tal (certificado autoassinado)" in text
    assert "15/10/2026 a 14/10/2029" in text
    assert "a assinatura cobre o documento inteiro" in text


def test_report_for_document_changed_after_signing():
    _app()
    info = _info(coverage="entire_revision", modification="other", docmdp_ok=False, revisions_after=1)

    text = format_signature_info(info, 1, 2)

    assert text.startswith('Assinatura 1 de 2 — campo "OpenFolioSignature"')
    assert "Resultado: INVÁLIDA" in text
    assert "1 revisão(ões) gravada(s) depois desta assinatura" in text
    assert "ALTERAÇÕES NO CONTEÚDO" in text
    # O trecho assinado em si está íntegro — e o relatório não esconde isso.
    assert "Conteúdo assinado: íntegro" in text


def test_report_for_trusted_signature_with_form_filling_afterwards():
    _app()
    info = _info(
        trusted=True,
        self_signed=False,
        issuer_name="AC Exemplo",
        coverage="entire_revision",
        modification="form_filling",
        revisions_after=1,
    )

    text = format_signature_info(info, 1, 1)

    assert "Resultado: VÁLIDA, COM RESSALVAS" in text
    assert "só preenchimento de formulário" in text
    assert "validado até uma autoridade certificadora confiável" in text


def test_report_for_signature_that_could_not_be_checked():
    _app()
    info = _info(intact=False, valid=False, error="estrutura inválida")

    text = format_signature_info(info, 1, 1)

    assert "Resultado: INVÁLIDA" in text
    assert "Não foi possível verificar esta assinatura: estrutura inválida" in text


def test_report_shows_reason_location_timestamp_and_format():
    _app()
    info = _info(reason="Aprovo", location="Curitiba", pades=True, timestamp="2026-10-22 10:00:00+00:00", timestamp_valid=False)

    text = format_signature_info(info, 1, 1)

    assert "Motivo: Aprovo" in text and "Local: Curitiba" in text and "Formato: PAdES" in text
    assert "Carimbo de tempo: 2026-10-22 10:00:00+00:00 (NÃO CONFERE)" in text
    assert "Contato" not in text  # vazio não aparece


def test_signature_tab_shows_the_certificate_and_signs_with_its_name(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from core.signature import DescribeSignatures
    from tests.test_signature import _appearance_bytes, _make_pdf, _pfx
    from ui.document_session import DocumentSession
    from ui.pages.signature_page import SignaturePage
    from ui.tasks import wait_for_tasks

    _app()
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    source, output = tmp_path / "doc.pdf", tmp_path / "assinado.pdf"
    _make_pdf(source, "Contrato")
    session = DocumentSession()
    session.open(str(source))
    page = SignaturePage(session)
    pfx_path = _pfx(tmp_path, "Ciclano", 30)
    monkeypatch.setattr(page.pfx_picker, "path", lambda: str(pfx_path))
    monkeypatch.setattr(page.sign_output_picker, "path", lambda: str(output))
    page.pfx_password_edit.setText("senha")

    page._show_certificate()
    assert wait_for_tasks()
    assert "Ciclano" in page.certificate_label.text() and "VENCIDO" not in page.certificate_label.text()

    page.reason_edit.setText("De acordo")
    page._apply_sign()
    assert wait_for_tasks()

    (info,) = DescribeSignatures().run(str(output))
    assert (info.signer_name, info.reason, info.pades) == ("Ciclano", "De acordo", True)
    assert b"Ciclano" in _appearance_bytes(output)
