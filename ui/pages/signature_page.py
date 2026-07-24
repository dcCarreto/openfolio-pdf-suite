"""Aba de assinatura digital: selo visível + assinatura criptográfica (CMS/PKCS#7),
com verificação de integridade."""

from pypdf import PdfReader
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.signature import DescribeSignatures, SignDocument
from ui.i18n import tr
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker

_POSITION_LABELS = ["Inferior direito", "Inferior esquerdo", "Superior direito", "Superior esquerdo"]
_POSITION_VALUES = {
    "Inferior direito": "bottom-right",
    "Inferior esquerdo": "bottom-left",
    "Superior direito": "top-right",
    "Superior esquerdo": "top-left",
}


class SignaturePage(QWidget):
    """Permite assinar digitalmente um PDF (selo visível + CMS/PKCS#7) ou verificar as
    assinaturas já presentes em um PDF assinado."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

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

        self.signer_name_edit = QLineEdit()
        self.signer_name_edit.setPlaceholderText(tr("Nome exibido na assinatura"))

        self.page_combo = QComboBox()
        self._refresh_page_combo()

        self.position_combo = QComboBox()
        self.position_combo.addItems([tr(label) for label in _POSITION_LABELS])

        self.sign_output_picker = FilePicker(mode="save")
        sign_button = QPushButton(tr("Assinar"))
        sign_button.clicked.connect(self._apply_sign)

        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Certificado:")))
        layout.addWidget(self.cert_mode_combo)
        layout.addWidget(self.cert_stack)
        layout.addWidget(QLabel(tr("Nome do signatário:")))
        layout.addWidget(self.signer_name_edit)
        layout.addWidget(QLabel(tr("Página:")))
        layout.addWidget(self.page_combo)
        layout.addWidget(QLabel(tr("Posição do selo:")))
        layout.addWidget(self.position_combo)
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

        layout.addWidget(QLabel(tr("Arquivo .pfx/.p12:")))
        layout.addWidget(self.pfx_picker)
        layout.addWidget(QLabel(tr("Senha:")))
        layout.addWidget(self.pfx_password_edit)
        return widget

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
        verify_button.clicked.connect(self._apply_verify)

        self.verify_result = QTextEdit()
        self.verify_result.setReadOnly(True)

        layout.addWidget(QLabel(tr("Arquivo PDF a verificar:")))
        layout.addWidget(self.verify_input_picker)
        layout.addWidget(verify_button)
        layout.addWidget(self.verify_result)
        return widget

    def _on_mode_changed(self, index: int):
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
        signer_name = self.signer_name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Assinar"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Assinar"), tr("Escolha o arquivo de saída."))
            return
        if not signer_name:
            QMessageBox.warning(self, tr("Assinar"), tr("Digite o nome do signatário."))
            return
        if self.page_combo.currentIndex() < 0:
            QMessageBox.warning(self, tr("Assinar"), tr("O PDF de entrada não tem páginas."))
            return

        position = _POSITION_VALUES[_POSITION_LABELS[self.position_combo.currentIndex()]]
        kwargs = {
            "signer_name": signer_name,
            "page_index": self.page_combo.currentIndex(),
            "position": position,
        }

        if self.cert_mode_combo.currentIndex() == 0:
            pfx_path = self.pfx_picker.path()
            if not pfx_path:
                QMessageBox.warning(self, tr("Assinar"), tr("Escolha o arquivo .pfx/.p12."))
                return
            kwargs["pfx_path"] = pfx_path
            kwargs["pfx_password"] = self.pfx_password_edit.text()
        else:
            test_name = self.test_name_edit.text().strip()
            if not test_name:
                QMessageBox.warning(self, tr("Assinar"), tr("Digite o nome para o certificado de teste."))
                return
            kwargs["test_common_name"] = test_name
            kwargs["test_email"] = self.test_email_edit.text().strip()

        try:
            SignDocument().run(input_path, output_path, **kwargs)
        except Exception as exc:
            QMessageBox.critical(self, tr("Assinar"), tr("Falha ao assinar: {error}").format(error=exc))
            return

        self.session.open(output_path)
        QMessageBox.information(self, tr("Assinar"), tr("PDF assinado com sucesso."))

    def _apply_verify(self):
        input_path = self.verify_input_picker.path()
        if not input_path:
            QMessageBox.warning(self, tr("Verificar assinatura"), tr("Escolha o arquivo PDF a verificar."))
            return

        try:
            signatures = DescribeSignatures().run(input_path)
        except Exception as exc:
            QMessageBox.critical(
                self, tr("Verificar assinatura"), tr("Falha ao verificar: {error}").format(error=exc)
            )
            return

        if not signatures:
            self.verify_result.setPlainText(tr("Nenhuma assinatura encontrada neste PDF."))
            return

        lines = []
        for info in signatures:
            status = tr("íntegro (não modificado)") if info.intact else tr("MODIFICADO após a assinatura")
            lines.append(
                tr("Campo: {field}\nSignatário: {signer}\nData: {date}\nStatus: {status}").format(
                    field=info.field_name, signer=info.signer_name, date=info.signing_time, status=status
                )
            )
        self.verify_result.setPlainText("\n\n".join(lines))
