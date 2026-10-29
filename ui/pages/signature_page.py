"""Aba de assinatura digital: selo visível + assinatura criptográfica (CMS/PKCS#7),
com verificação de integridade."""

from pypdf import PdfReader
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.signature import (
    VERDICT_INVALID,
    VERDICT_VALID,
    VERDICT_WARNING,
    DescribeSignatures,
    SignatureInfo,
    SignDocument,
    describe_certificate,
)
from ui import i18n
from ui.area_pick_state import AreaPickState
from ui.i18n import plural, tr, tr_message
from ui.tasks import call, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker
from ui.tool_panel import notify_error, notify_success

_POSITION_LABELS = [
    "Inferior direito",
    "Inferior esquerdo",
    "Superior direito",
    "Superior esquerdo",
    "Área marcada no visualizador",
]
_POSITION_VALUES = {
    "Inferior direito": "bottom-right",
    "Inferior esquerdo": "bottom-left",
    "Superior direito": "top-right",
    "Superior esquerdo": "top-left",
    "Área marcada no visualizador": "custom",
}
_CUSTOM_POSITION = len(_POSITION_LABELS) - 1
_SIGN_MODE = 0

_VERDICT_LABELS = {
    VERDICT_VALID: "VÁLIDA",
    VERDICT_WARNING: "VÁLIDA, COM RESSALVAS",
    VERDICT_INVALID: "INVÁLIDA",
}
_MODIFICATION_LABELS = {
    "none": "sem mudança de conteúdo",
    "lta_updates": "só manutenção de assinaturas (carimbos de tempo e dados de validação)",
    "form_filling": "só preenchimento de formulário e novas assinaturas",
    "annotations": "comentários e anotações",
    "other": "ALTERAÇÕES NO CONTEÚDO — o documento pode ter sido adulterado depois de assinado",
    "unknown": "não foi possível analisar o que mudou",
}


def _format_date(iso_date: str) -> str:
    if not iso_date or i18n.get_language() != i18n.PT_BR:
        return iso_date
    year, month, day = iso_date.split("-")
    return f"{day}/{month}/{year}"


def _describe_changes(info: SignatureInfo) -> str:
    if info.coverage == "entire_file":
        return tr("nenhuma — a assinatura cobre o documento inteiro")
    if info.coverage != "entire_revision":
        return tr("a assinatura não cobre o documento de forma padrão — trate como suspeito")
    revisions = plural(
        info.revisions_after,
        "1 revisão gravada depois desta assinatura",
        "{count} revisões gravadas depois desta assinatura",
    )
    return f"{revisions}: {tr(_MODIFICATION_LABELS[info.modification])}"


def _describe_trust(info: SignatureInfo) -> str:
    if info.trusted:
        return tr("validado até uma autoridade certificadora confiável do sistema")
    if info.self_signed:
        return tr("não confiável — certificado autoassinado (sem validade jurídica)")
    return tr(
        "não confiável — não foi possível validar a cadeia até uma autoridade confiável do "
        "sistema (para certificados ICP-Brasil, a cadeia da ICP-Brasil precisa estar instalada)"
    )


def format_signature_info(info: SignatureInfo, number: int, total: int) -> str:
    """Relatório de uma assinatura, do veredito para os detalhes."""
    lines = [
        tr('Assinatura {number} de {total} — campo "{field}"').format(
            number=number, total=total, field=info.field_name
        ),
        tr("Resultado: {verdict}").format(verdict=tr(_VERDICT_LABELS[info.verdict])),
    ]
    if info.error:
        lines.append(tr("Não foi possível verificar esta assinatura: {error}").format(error=tr_message(info.error)))
        return "\n".join(lines)

    issuer = (
        tr("{name} (certificado autoassinado)").format(name=info.issuer_name)
        if info.self_signed
        else info.issuer_name
    )
    lines.append(tr("Signatário (segundo o certificado): {name}").format(name=info.signer_name))
    lines.append(tr("Emitido por: {issuer}").format(issuer=issuer))
    lines.append(
        tr("Validade do certificado: {start} a {end}").format(
            start=_format_date(info.cert_valid_from), end=_format_date(info.cert_valid_until)
        )
    )
    if info.signing_time:
        lines.append(tr("Data declarada pelo signatário: {date}").format(date=info.signing_time))
    if info.timestamp:
        status = tr("confere") if info.timestamp_valid else tr("NÃO CONFERE")
        lines.append(tr("Carimbo de tempo: {date} ({status})").format(date=info.timestamp, status=status))
    for label, value in (("Motivo: {value}", info.reason), ("Local: {value}", info.location), ("Contato: {value}", info.contact)):
        if value:
            lines.append(tr(label).format(value=value))
    if info.pades:
        lines.append(tr("Formato: PAdES"))
    lines.append(
        tr("Conteúdo assinado: {status}").format(
            status=tr("íntegro") if info.intact else tr("ALTERADO depois da assinatura")
        )
    )
    lines.append(
        tr("Assinatura criptográfica: {status}").format(
            status=tr("válida") if info.valid else tr("INVÁLIDA")
        )
    )
    lines.append(tr("Alterações depois da assinatura: {status}").format(status=_describe_changes(info)))
    lines.append(tr("Confiança no certificado: {status}").format(status=_describe_trust(info)))
    return "\n".join(lines)


class SignaturePage(QWidget):
    """Permite assinar digitalmente um PDF (selo visível + CMS/PKCS#7) ou verificar as
    assinaturas já presentes em um PDF assinado."""

    def __init__(self, session, area_pick_state: AreaPickState | None = None, parent=None):
        super().__init__(parent)
        self.action_buttons: list[QPushButton] = []  # a ação de cada modo, no rodapé do painel
        self.session = session
        self.area_pick_state = area_pick_state or AreaPickState()
        self.area_pick_state.area_picked.connect(self._on_area_picked)
        self._stamp_area: tuple[int, tuple[float, float, float, float]] | None = None

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Assinar"), tr("Verificar assinatura")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_sign_panel())
        self.stack.addWidget(self._build_verify_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)
        self.area_pick_state.set_wanted(self, True)

    def _on_area_picked(self, page_index: int, left: float, bottom: float, right: float, top: float):
        if self.area_pick_state.owner() is not self:
            return
        self._stamp_area = (page_index, (left, bottom, right, top))
        if 0 <= page_index < self.page_combo.count():
            self.page_combo.setCurrentIndex(page_index)
        self.position_combo.setCurrentIndex(_CUSTOM_POSITION)
        self.area_pick_state.set_areas(self, [self._stamp_area], 0)

    def _build_sign_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.source_bar = DocumentSourceBar(self.session)
        self.session.path_changed.connect(self._refresh_page_combo)

        self.cert_mode_combo = QComboBox()
        self.cert_mode_combo.addItems([tr("Arquivo .pfx"), tr("Gerar certificado de teste")])
        self.cert_mode_combo.currentIndexChanged.connect(self._on_cert_mode_changed)

        self.cert_stack = QStackedWidget()
        self.cert_stack.addWidget(self._build_pfx_panel())
        self.cert_stack.addWidget(self._build_test_cert_panel())

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(tr("Opcional, ex: Aprovo este documento"))
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText(tr("Opcional, ex: Curitiba, PR"))
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText(tr("Opcional, ex: telefone ou e-mail"))
        self.stamp_image_picker = FilePicker(mode="open", file_filter=tr("Imagens") + " (*.png *.jpg *.jpeg)")
        self.stamp_image_picker.setToolTip(
            tr("Opcional: a imagem da sua assinatura (PNG com fundo transparente fica melhor) na metade esquerda do selo.")
        )
        self.pades_check = QCheckBox(tr("Formato PAdES"))
        self.pades_check.setChecked(True)
        self.pades_check.setToolTip(
            tr("O padrão europeu de assinatura de PDF (ETSI). Desmarque só se um sistema antigo exigir o formato da Adobe.")
        )
        self.timestamp_edit = QLineEdit()
        self.timestamp_edit.setPlaceholderText(tr("Opcional: endereço do servidor de carimbo de tempo (TSA)"))
        self.timestamp_edit.setToolTip(
            tr(
                "Um servidor de carimbo de tempo atesta a data da assinatura, em vez do relógio deste "
                "computador. O app envia a ele só o resumo criptográfico do documento, não o documento."
            )
        )
        details = QFormLayout()
        details.addRow(tr("Motivo:"), self.reason_edit)
        details.addRow(tr("Local:"), self.location_edit)
        details.addRow(tr("Contato:"), self.contact_edit)
        details.addRow(tr("Imagem no selo:"), self.stamp_image_picker)
        details.addRow(tr("Carimbo de tempo:"), self.timestamp_edit)
        details.addRow("", self.pades_check)

        self.page_combo = QComboBox()
        self._refresh_page_combo()

        self.position_combo = QComboBox()
        self.position_combo.addItems([tr(label) for label in _POSITION_LABELS])
        position_hint = QLabel(tr("Para escolher o lugar exato do selo, arraste no visualizador."))
        position_hint.setWordWrap(True)

        self.sign_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="assinado", working_copy=False
        )
        sign_button = QPushButton(tr("Assinar"))
        self.action_buttons.append(sign_button)
        sign_button.clicked.connect(self._apply_sign)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        # O que diferencia este modo do "Assinar à mão" (que não usa certificado).
        validity = QLabel(
            tr("Assinatura com validade criptográfica: quem receber o PDF consegue conferir quem assinou e se ele mudou depois.")
        )
        validity.setObjectName("SignatureValidity")
        validity.setProperty("ofRole", "help")
        validity.setWordWrap(True)
        layout.addWidget(validity)
        layout.addWidget(QLabel(tr("Certificado:")))
        layout.addWidget(self.cert_mode_combo)
        layout.addWidget(self.cert_stack)
        layout.addLayout(details)
        layout.addWidget(QLabel(tr("Página:")))
        layout.addWidget(self.page_combo)
        layout.addWidget(QLabel(tr("Posição do selo:")))
        layout.addWidget(self.position_combo)
        layout.addWidget(position_hint)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.sign_output_picker)
        layout.addWidget(sign_button)
        return widget

    def _build_pfx_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pfx_picker = FilePicker(mode="open", file_filter=tr("Certificado (*.pfx *.p12)"))
        self.pfx_password_edit = QLineEdit()
        self.pfx_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pfx_password_edit.setPlaceholderText(tr("Senha do certificado"))

        show_button = QPushButton(tr("Ver o certificado"))
        show_button.setToolTip(tr("Mostra de quem é o certificado, quem o emitiu e até quando vale."))
        show_button.clicked.connect(self._show_certificate)
        password_row = QHBoxLayout()
        password_row.addWidget(self.pfx_password_edit, 1)
        password_row.addWidget(show_button)
        self.certificate_label = QLabel(tr("O selo leva o nome que está no certificado."))
        self.certificate_label.setWordWrap(True)

        layout.addWidget(QLabel(tr("Arquivo .pfx/.p12:")))
        layout.addWidget(self.pfx_picker)
        layout.addWidget(QLabel(tr("Senha:")))
        layout.addLayout(password_row)
        layout.addWidget(self.certificate_label)
        return widget

    def _show_certificate(self):
        pfx_path = self.pfx_picker.path()
        if not pfx_path:
            notify_error(self, tr("Assinar"), tr("Escolha o arquivo .pfx/.p12."))
            return

        def done(summary):
            lines = [
                tr("Signatário (segundo o certificado): {name}").format(name=summary.name),
                tr("Emitido por: {issuer}").format(
                    issuer=tr("{name} (certificado autoassinado)").format(name=summary.issuer_name)
                    if summary.self_signed
                    else summary.issuer_name
                ),
                tr("Validade do certificado: {start} a {end}").format(
                    start=_format_date(summary.valid_from), end=_format_date(summary.valid_until)
                ),
            ]
            if summary.expired:
                lines.append(tr("VENCIDO: não dá para assinar com ele."))
            self.certificate_label.setText("\n".join(lines))

        run_task(
            self,
            tr("Assinar"),
            call(describe_certificate, pfx_path, self.pfx_password_edit.text()),
            on_success=done,
            error_message=tr("Falha ao abrir o certificado: {error}"),
        )

    def _build_test_cert_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        warning = QLabel(
            tr(
                "Certificado autoassinado gerado na hora, sem validade jurídica — use só "
                "para testar o fluxo ou assinaturas de uso pessoal/interno."
            )
        )
        warning.setWordWrap(True)

        self.test_name_edit = QLineEdit()
        self.test_name_edit.setPlaceholderText(tr("Nome completo"))
        self.test_email_edit = QLineEdit()
        self.test_email_edit.setPlaceholderText(tr("E-mail"))

        layout.addWidget(warning)
        layout.addWidget(QLabel(tr("Nome:")))
        layout.addWidget(self.test_name_edit)
        layout.addWidget(QLabel(tr("E-mail:")))
        layout.addWidget(self.test_email_edit)
        return widget

    def _build_verify_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.verify_input_picker = FilePicker(mode="open")
        verify_button = QPushButton(tr("Verificar"))
        self.action_buttons.append(verify_button)
        verify_button.clicked.connect(self._apply_verify)

        self.verify_result = QTextEdit()
        self.verify_result.setReadOnly(True)

        layout.addWidget(QLabel(tr("Arquivo PDF a verificar (vazio = o documento aberto):")))
        layout.addWidget(self.verify_input_picker)
        layout.addWidget(verify_button)
        layout.addWidget(self.verify_result)
        return widget

    def _on_mode_changed(self, index: int):
        self.area_pick_state.set_wanted(self, index == _SIGN_MODE)
        self.stack.setCurrentIndex(index)

    def _on_cert_mode_changed(self, index: int):
        self.cert_stack.setCurrentIndex(index)

    def _refresh_page_combo(self):
        self.page_combo.clear()
        path = self.session.path()
        if not path:
            return
        try:
            page_count = len(PdfReader(path).pages)
        except Exception:
            return
        self.page_combo.addItems(
            [tr("Página {number}").format(number=i + 1) for i in range(page_count)]
        )
        self.page_combo.setCurrentIndex(page_count - 1)  # última página, destino comum

    def _apply_sign(self):
        input_path = self.session.path()
        output_path = self.sign_output_picker.path()

        if not input_path:
            notify_error(self, tr("Assinar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            notify_error(self, tr("Assinar"), tr("Escolha o arquivo de saída."))
            return
        if self.page_combo.currentIndex() < 0:
            notify_error(self, tr("Assinar"), tr("O PDF de entrada não tem páginas."))
            return

        position = _POSITION_VALUES[_POSITION_LABELS[self.position_combo.currentIndex()]]
        kwargs = {
            "page_index": self.page_combo.currentIndex(),
            "position": position,
            "reason": self.reason_edit.text(),
            "location": self.location_edit.text(),
            "contact": self.contact_edit.text(),
            "timestamp_url": self.timestamp_edit.text(),
            "pades": self.pades_check.isChecked(),
            "stamp_image": self.stamp_image_picker.path() or None,
        }
        if position == "custom":
            if self._stamp_area is None:
                notify_error(self, tr("Assinar"), tr("Arraste no visualizador para marcar a área do selo."))
                return
            kwargs["page_index"], kwargs["box"] = self._stamp_area
            kwargs["position"] = "bottom-right"  # ignorada quando há `box`

        if self.cert_mode_combo.currentIndex() == 0:
            pfx_path = self.pfx_picker.path()
            if not pfx_path:
                notify_error(self, tr("Assinar"), tr("Escolha o arquivo .pfx/.p12."))
                return
            kwargs["pfx_path"] = pfx_path
            kwargs["pfx_password"] = self.pfx_password_edit.text()
        else:
            test_name = self.test_name_edit.text().strip()
            if not test_name:
                notify_error(self, tr("Assinar"), tr("Digite o nome para o certificado de teste."))
                return
            kwargs["test_common_name"] = test_name
            kwargs["test_email"] = self.test_email_edit.text().strip()

        task = call(SignDocument().run, input_path, output_path, **kwargs)

        def done(_result):
            self.pfx_password_edit.clear()  # depois de assinar; "Ver o certificado" ainda usa
            self.session.open(output_path)
            notify_success(self, tr("Assinar"), tr("PDF assinado com sucesso."))

        run_task(
            self,
            tr("Assinar"),
            task,
            on_success=done,
            error_message=tr("Falha ao assinar: {error}"),
        )

    def _apply_verify(self):
        input_path = self.verify_input_picker.path() or self.session.path()
        if not input_path:
            notify_error(self, tr("Verificar assinatura"), tr("Escolha o arquivo PDF a verificar."))
            return

        task = call(DescribeSignatures().run, input_path)

        def done(signatures):
            if not signatures:
                self.verify_result.setPlainText(tr("Nenhuma assinatura encontrada neste PDF."))
                return

            reports = [
                format_signature_info(info, number, len(signatures))
                for number, info in enumerate(signatures, start=1)
            ]
            self.verify_result.setPlainText("\n\n".join(reports))

        run_task(
            self,
            tr("Verificar assinatura"),
            task,
            on_success=done,
            error_message=tr("Falha ao verificar: {error}"),
        )
