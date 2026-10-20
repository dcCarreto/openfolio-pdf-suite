"""Arquivo > Propriedades do documento (A12): geral, segurança, fontes e páginas."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.properties import DocumentProperties
from ui.i18n import PT_BR, get_language, tr, tr_message
from ui.page_ranges import format_page_ranges

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


class DocumentPropertiesDialog(QDialog):
    def __init__(self, properties: DocumentProperties, file_name: str, modified: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Propriedades do documento"))
        self.resize(640, 520)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(properties, file_name, modified), tr("Geral"))
        tabs.addTab(self._security_tab(properties), tr("Segurança"))
        tabs.addTab(self._fonts_tab(properties), tr("Fontes"))
        tabs.addTab(self._pages_tab(properties), tr("Páginas"))
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
                ("Autor:", meta["author"]),
                ("Assunto:", meta["subject"]),
                ("Palavras-chave:", meta["keywords"]),
                ("Criado com:", meta["creator"]),
                ("Produtor do PDF:", meta["producer"]),
                ("Criado em:", date(meta["created"])),
                ("Modificado em:", date(meta["modified"])),
                ("Visualização rápida na web:", _yes_no(p.linearized)),
                ("Marcado para acessibilidade:", _yes_no(p.tagged)),
                ("PDF/A:", p.pdfa or tr("Não declara")),
                ("Formulário:", form or tr("Não tem")),
            ]
        )

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
