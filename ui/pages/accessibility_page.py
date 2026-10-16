"""Aba de acessibilidade: verifica um subconjunto de PDF/UA e corrige idioma/título."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.accessibility import CheckAccessibility, FixBasicAccessibilityIssues
from ui.i18n import tr
from ui.tasks import call, run_task
from ui.widgets.document_source_bar import DocumentSourceBar
from ui.widgets.file_picker import FilePicker


class AccessibilityPage(QWidget):
    """Permite verificar um subconjunto dos requisitos de acessibilidade (PDF/UA) de um
    PDF, e corrigir idioma/título do documento — os únicos ajustes seguros de aplicar
    automaticamente sem risco de corromper o conteúdo."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.source_bar = DocumentSourceBar(session)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Verificar"), tr("Corrigir idioma/título")])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_check_panel())
        self.stack.addWidget(self._build_fix_panel())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Arquivo PDF de entrada:")))
        layout.addWidget(self.source_bar)
        layout.addWidget(QLabel(tr("Modo:")))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)

    def _build_check_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Verifica só um subconjunto dos requisitos de PDF/UA (idioma, título, "
                "árvore de estrutura e texto alternativo em figuras já tagueadas) — não é "
                "validação PDF/UA completa."
            )
        )
        note.setWordWrap(True)

        check_button = QPushButton(tr("Verificar"))
        check_button.clicked.connect(self._check)

        layout.addWidget(note)
        layout.addWidget(check_button)
        return widget

    def _build_fix_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            tr(
                "Não tagueia o documento automaticamente (risco real de gerar uma estrutura "
                "malformada e passar uma falsa sensação de acessibilidade) — só ajusta "
                "idioma e título, os dois únicos itens que são simples metadados."
            )
        )
        note.setWordWrap(True)

        self.fix_output_picker = FilePicker(
            mode="save", suggested_source=self.session.path, suggested_suffix="acessivel"
        )
        self.fix_language_edit = QLineEdit()
        self.fix_language_edit.setPlaceholderText(tr("Idioma, ex: pt-BR"))
        self.fix_title_edit = QLineEdit()
        self.fix_title_edit.setPlaceholderText(tr("Título do documento"))

        fix_button = QPushButton(tr("Corrigir"))
        fix_button.clicked.connect(self._fix)

        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Arquivo de saída:")))
        layout.addWidget(self.fix_output_picker)
        layout.addWidget(QLabel(tr("Idioma:")))
        layout.addWidget(self.fix_language_edit)
        layout.addWidget(QLabel(tr("Título:")))
        layout.addWidget(self.fix_title_edit)
        layout.addWidget(fix_button)
        return widget

    def _on_mode_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _check(self):
        input_path = self.session.path()
        if not input_path:
            QMessageBox.warning(self, tr("Acessibilidade"), tr("Abra um PDF para começar."))
            return

        task = call(CheckAccessibility().run, input_path)

        def done(report):
            if report.is_compliant:
                QMessageBox.information(
                    self, tr("Acessibilidade"), tr("Nenhum problema encontrado nas verificações realizadas.")
                )
            else:
                issues_text = "\n".join(f"• {issue}" for issue in report.issues)
                QMessageBox.warning(
                    self, tr("Acessibilidade"), tr("Problemas encontrados:\n{issues}").format(issues=issues_text)
                )

        run_task(
            self,
            tr("Acessibilidade"),
            task,
            on_success=done,
            error_message=tr("Falha ao verificar: {error}"),
        )

    def _fix(self):
        input_path = self.session.path()
        output_path = self.fix_output_picker.path()
        language = self.fix_language_edit.text().strip()
        title = self.fix_title_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, tr("Acessibilidade"), tr("Abra um PDF para começar."))
            return
        if not output_path:
            QMessageBox.warning(self, tr("Acessibilidade"), tr("Escolha o arquivo de saída."))
            return
        if not language or not title:
            QMessageBox.warning(self, tr("Acessibilidade"), tr("Informe o idioma e o título."))
            return

        task = call(FixBasicAccessibilityIssues().run, input_path, output_path, language=language, title=title)

        def done(_result):
            self.session.open(output_path)
            QMessageBox.information(self, tr("Acessibilidade"), tr("Idioma e título corrigidos com sucesso."))

        run_task(
            self,
            tr("Acessibilidade"),
            task,
            on_success=done,
            error_message=tr("Falha ao corrigir: {error}"),
        )
