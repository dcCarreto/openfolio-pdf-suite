"""Arquivo > Propriedades do documento (A12, M29): geral, descrição (editável), segurança,
fontes, páginas, XMP (editável), PDF/A e acessibilidade.

O que é editado aqui é gravado numa versão nova do documento de trabalho, como nas abas
(Ctrl+Z desfaz), e o diálogo fecha: as propriedades mostradas eram as da versão anterior.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.accessibility import CheckAccessibility
from core.metadata import SetMetadata, SetXMP
from core.pdfa import ValidatePDFA
from core.properties import DocumentProperties
from ui.i18n import PT_BR, get_language, tr, tr_message
from ui.page_ranges import format_page_ranges
from ui.tasks import call, call_with_progress, run_task

_DESCRIPTION_FIELDS = [
    ("title", "Título:"),
    ("author", "Autor:"),
    ("subject", "Assunto:"),
    ("keywords", "Palavras-chave:"),
    ("creator", "Criado com:"),
    ("producer", "Produtor do PDF:"),
]

_PERMISSION_LABELS = {
    "print": "Imprimir:",
    "print_high_quality": "Imprimir em alta qualidade:",
    "modify": "Alterar o documento:",
    "copy": "Copiar texto e imagens:",
    "accessibility": "Extrair texto para acessibilidade:",
    "annotate": "Comentar:",
    "fill_forms": "Preencher formulários:",
    "assemble": "Montar o documento (inserir, girar, excluir páginas):",
}

# Nome, (largura, altura) em pontos, em retrato.
_PAPERS = [
    ("A3", (842, 1191)),
    ("A4", (595, 842)),
    ("A5", (420, 595)),
    ("Carta (Letter)", (612, 792)),
    ("Ofício (Legal)", (612, 1008)),
]


def _number(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    if get_language() == PT_BR:
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def format_file_size(size: int) -> str:
    """1234567 -> "1,2 MB (1.234.567 bytes)"."""
    exact = tr("{count} bytes").format(count=_number(size, 0))
    for unit, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size >= factor:
            return f"{_number(size / factor)} {unit} ({exact})"
    return exact


def describe_page_size(width: float, height: float) -> str:
    """Tamanho em mm, com o nome do papel e a orientação: "210 × 297 mm (A4, retrato)"."""
    to_mm = 25.4 / 72
    text = f"{_number(width * to_mm, 0)} × {_number(height * to_mm, 0)} mm"
    portrait = (min(width, height), max(width, height))
    paper = next((name for name, size in _PAPERS if all(abs(a - b) <= 2 for a, b in zip(portrait, size))), None)
    orientation = "" if abs(width - height) < 1 else tr("retrato") if height > width else tr("paisagem")
    details = [part for part in (tr(paper) if paper else "", orientation) if part]
    return f"{text} ({', '.join(details)})" if details else text


def _yes_no(value: bool) -> str:
    return tr("Sim") if value else tr("Não")


def _bullets(issues) -> str:
    return "\n".join("• " + tr_message(issue) for issue in issues)


class DocumentPropertiesDialog(QDialog):
    def __init__(self, properties: DocumentProperties, file_name: str, modified: bool, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Propriedades do documento"))
        self.resize(640, 520)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(properties, file_name, modified), tr("Geral"))
        tabs.addTab(self._description_tab(properties), tr("Descrição"))
        tabs.addTab(self._security_tab(properties), tr("Segurança"))
        tabs.addTab(self._fonts_tab(properties), tr("Fontes"))
        tabs.addTab(self._pages_tab(properties), tr("Páginas"))
        tabs.addTab(self._xmp_tab(properties), tr("XMP"))
        tabs.addTab(self._check_tab(self._check_pdfa, properties.pdfa or tr("Não declara")), tr("PDF/A"))
        tabs.addTab(self._check_tab(self._check_accessibility), tr("Acessibilidade"))
        self.tabs = tabs

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    @staticmethod
    def _form(rows: list[tuple[str, str]]) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        for label, value in rows:
            value_label = QLabel(value or "—")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(tr(label), value_label)
        return widget

    def _general_tab(self, p: DocumentProperties, file_name: str, modified: bool) -> QWidget:
        meta = p.metadata

        def date(moment):
            return moment.strftime("%d/%m/%Y %H:%M") if moment is not None else ""

        size = format_file_size(p.file_size)
        if modified:
            size += " " + tr("(com as alterações ainda não salvas)")
        form = "" if not p.form_fields else tr("{count} campo(s)").format(count=p.form_fields)
        if p.xfa:
            form = (form + " · " if form else "") + tr("XFA (formulário dinâmico, que o app não preenche)")
        return self._form(
            [
                ("Arquivo:", file_name),
                ("Tamanho:", size),
                ("Páginas:", str(p.page_count)),
                ("Versão do PDF:", p.version),
                ("Título:", meta["title"]),
                ("Criado em:", date(meta["created"])),
                ("Modificado em:", date(meta["modified"])),
                ("Visualização rápida na web:", _yes_no(p.linearized)),
                ("Marcado para acessibilidade:", _yes_no(p.tagged)),
                ("PDF/A:", p.pdfa or tr("Não declara")),
                ("Formulário:", form or tr("Não tem")),
            ]
        )

    # ---- Editáveis --------------------------------------------------------------------

    def _description_tab(self, p: DocumentProperties) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.description_edits: dict[str, QLineEdit] = {}
        for key, label in _DESCRIPTION_FIELDS:
            edit = QLineEdit(p.metadata[key])
            form.addRow(tr(label), edit)
            self.description_edits[key] = edit
        save_button = QPushButton(tr("Salvar a descrição"))
        save_button.clicked.connect(self._save_description)
        form.addRow("", save_button)
        return widget

    def _xmp_tab(self, p: DocumentProperties) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        note = QLabel(
            tr(
                "O pacote XMP completo, como está no arquivo. Se ele existe, salvar a Descrição "
                "grava os mesmos campos nele; uma mudança feita só aqui não muda a Descrição. "
                "Vazio tira o XMP."
            )
        )
        note.setWordWrap(True)
        self.xmp_edit = QPlainTextEdit(p.xmp)
        self.xmp_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.xmp_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        save_button = QPushButton(tr("Salvar o XMP"))
        save_button.clicked.connect(self._save_xmp)
        layout.addWidget(note)
        layout.addWidget(self.xmp_edit)
        layout.addWidget(save_button)
        return widget

    def _apply(self, operation) -> bool:
        """Roda `operation(entrada, saída)` numa versão nova do documento de trabalho."""
        input_path = self.session.path()
        if not input_path:
            return False
        output_path = self.session.new_version_path()

        def done(_result):
            self.session.open(output_path)
            self.accept()
            QMessageBox.information(self.parentWidget(), tr("Propriedades do documento"), tr("Propriedades salvas."))

        return run_task(
            self,
            tr("Propriedades do documento"),
            call(operation, input_path, output_path),
            on_success=done,
            error_message=tr("Falha ao salvar as propriedades: {error}"),
        )

    def _save_description(self) -> bool:
        values = {key: edit.text().strip() for key, edit in self.description_edits.items()}
        return self._apply(lambda source, output: SetMetadata().run(source, output, **values))

    def _save_xmp(self) -> bool:
        xmp = self.xmp_edit.toPlainText()
        return self._apply(lambda source, output: SetXMP().run(source, output, xmp))

    # ---- Verificações ---------------------------------------------------------------

    def _check_tab(self, check, declared: str | None = None) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        if declared is not None:
            layout.addWidget(QLabel(tr("Declara: {pdfa}").format(pdfa=declared)))
        result = QPlainTextEdit()
        result.setReadOnly(True)
        button = QPushButton(tr("Verificar"))
        button.clicked.connect(lambda: check(result))
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(result)
        return widget

    def _run_check(self, output: QPlainTextEdit, task, ok_text: str) -> bool:
        def done(result):
            ok = getattr(result, "is_valid", getattr(result, "is_compliant", False))
            output.setPlainText(ok_text if ok else tr("Problemas encontrados:\n{issues}").format(issues=_bullets(result.issues)))

        return run_task(self, tr("Propriedades do documento"), task, on_success=done, error_message=tr("Falha ao verificar: {error}"))

    def _check_pdfa(self, output: QPlainTextEdit) -> bool:
        return self._run_check(
            output,
            call_with_progress(ValidatePDFA().run, self.session.path()),
            tr("Os requisitos de PDF/A que o app verifica foram atendidos. Para converter, use a ferramenta PDF/A."),
        )

    def _check_accessibility(self, output: QPlainTextEdit) -> bool:
        return self._run_check(
            output,
            call(CheckAccessibility().run, self.session.path()),
            tr("Nenhum problema nos itens de acessibilidade que o app verifica."),
        )

    # ---- Só leitura ---------------------------------------------------------------------

    def _security_tab(self, p: DocumentProperties) -> QWidget:
        if p.permissions is None:
            return self._form([("Proteção:", tr("Sem proteção: qualquer pessoa abre, imprime, copia e altera."))])
        rows = [
            ("Proteção:", tr("Criptografia {method}").format(method=p.encryption)),
            ("Senha para abrir:", _yes_no(p.needs_password)),
        ]
        for key, allowed in p.permissions.items():
            rows.append((_PERMISSION_LABELS[key], tr("Permitido") if allowed else tr("Não permitido")))
        return self._form(rows)

    def _fonts_tab(self, p: DocumentProperties) -> QWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("Fonte"), tr("Tipo"), tr("Embutida"), tr("Codificação"), tr("Páginas")])
        tree.setRootIsDecorated(False)
        missing = 0
        for font in p.fonts:
            if font.embedded:
                embedded = tr("Sim (subconjunto)") if font.subset else tr("Sim")
            else:
                embedded = tr("Não (fonte padrão)") if font.standard else tr("Não")
                missing += not font.standard
            tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        font.name or tr("(sem nome)"),
                        font.kind,
                        embedded,
                        tr_message(font.encoding),
                        format_page_ranges(font.pages),
                    ]
                )
            )
        for column in range(tree.columnCount()):
            tree.resizeColumnToContents(column)
        self.fonts_tree = tree

        if not p.fonts:
            summary = tr("Nenhuma fonte: o documento não tem texto (escaneado ou só imagens).")
        else:
            summary = tr("{count} fonte(s).").format(count=len(p.fonts))
            if missing:
                summary += " " + tr(
                    "{count} não embutida(s): em outro computador, o texto pode aparecer com outra fonte."
                ).format(count=missing)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(summary)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(tree)
        return widget

    def _pages_tab(self, p: DocumentProperties) -> QWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("Tamanho"), tr("Páginas")])
        tree.setRootIsDecorated(False)
        for group in p.page_sizes:
            tree.addTopLevelItem(
                QTreeWidgetItem([describe_page_size(group.width, group.height), format_page_ranges(group.pages)])
            )
        tree.resizeColumnToContents(0)
        self.pages_tree = tree
        return tree
