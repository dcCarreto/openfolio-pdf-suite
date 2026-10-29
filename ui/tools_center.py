"""A aba Ferramentas: as 23 ferramentas em 8 grupos, numa grade de 4 colunas x 2 linhas que cabe
inteira em 1280 x 720, com as "Mais usadas" em cima e um campo de busca grande que filtra os
cartões no lugar (com sinônimos; ver ui/search_index.py)."""

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ui import search_index, sidebar_icons
from ui.i18n import literal, tr
from ui.icon_utils import in_accent
from ui.preferences import preferences
from ui.tools import GROUPS, TOOLS
from ui.viewer.viewer_icons import build_pin_icon, build_search_icon

MAX_WIDTH = 1200
COLUMNS = 4
DEFAULT_FAVORITES = ["CompressPage", "MergePage", "FillSignPage", "ConvertPage", "OrganizePage"]
_AUTOMATE_NOTE = "Escolha uma pasta e uma operação; no fim, um relatório CSV mostra o que deu certo."


def most_used(count: int = 5) -> list[str]:
    """As ferramentas mais abertas; sem uso ainda, as de fábrica completam a lista."""
    uses = preferences().tool_uses()
    ranked = sorted(uses, key=lambda tool: -uses[tool])
    return [*ranked, *(tool for tool in DEFAULT_FAVORITES if tool not in ranked)][:count]


def tool_tip(tool_id: str) -> str:
    """A dica rica de uma ferramenta: o nome, uma frase sobre o efeito e os modos."""
    tool = TOOLS[tool_id]
    text = f"<b>{tr(tool.title)}</b><br>{tr(tool.description)}"
    if len(tool.modes) > 1:
        modes = ", ".join(tr(mode.label) for mode in tool.modes)
        text += "<br><span>" + tr("Modos: {modes}").format(modes=modes) + "</span>"
    return text


class ToolRow(QToolButton):
    """Uma ferramenta no cartão do grupo: ícone, nome (uma linha), o motivo da busca ("por
    “cpf”") e o alfinete das que estão na coluna rápida."""

    def __init__(self, tool_id: str, parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        tool = TOOLS[tool_id]
        self.setObjectName("ToolRow")
        self.setIcon(getattr(sidebar_icons, tool.icon)())
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.reason = QLabel()
        self.reason.setObjectName("ToolReason")
        self.pin = QLabel()
        self.pin.setPixmap(build_pin_icon().pixmap(QSize(13, 13), QIcon.Mode.Disabled))
        for label in (self.reason, self.pin):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)
        layout.addStretch()
        layout.addWidget(self.reason)
        layout.addWidget(self.pin)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.retranslate()

    def retranslate(self):
        tool = TOOLS[self.tool_id]
        self.name = tr(tool.title)
        self.setToolTip(tool_tip(self.tool_id))
        self.setAccessibleName(self.name)
        self.setAccessibleDescription(tr(tool.description))
        self._fit_name()

    def text(self) -> str:  # type: ignore[override]
        """O nome inteiro, mesmo quando a linha mostra com reticências."""
        return self.name

    def _fit_name(self) -> None:
        """O nome numa linha só, com reticências se não couber antes do motivo e do alfinete."""
        extras = [label for label in (self.reason, self.pin) if not label.isHidden()]
        right = sum(label.sizeHint().width() + 6 for label in extras) + (8 if extras else 0)
        available = self.width() - right - self.iconSize().width() - 22  # bordas, padding e o vão do ícone
        shown = self.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight, max(available, 20))
        super().setText(literal(shown))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_name()

    def set_pinned(self, pinned: bool) -> None:
        self.pin.setVisible(pinned)
        self.pin.setToolTip(tr("Na coluna rápida") if pinned else "")
        self._fit_name()

    def set_reason(self, reason: str) -> None:
        self.reason.setText(tr("por “{word}”").format(word=reason) if reason else "")
        self.reason.setVisible(bool(reason))
        self._fit_name()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # No foco do teclado, a dica rica aparece à direita da linha, como com o mouse.
        if event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.OtherFocusReason):
            QToolTip.showText(self.mapToGlobal(QPoint(self.width() + 4, 0)), self.toolTip(), self)


class GroupCard(QFrame):
    """Um grupo: placa com o ícone da primeira ferramenta, o nome, a frase de apoio e as linhas."""

    def __init__(self, name: str, phrase: str, tool_ids: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("GroupCard")
        self.name = name
        tile = QLabel()
        tile.setObjectName("IconTile")
        tile.setFixedSize(32, 32)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(getattr(sidebar_icons, TOOLS[tool_ids[0]].icon)().pixmap(QSize(19, 19), QIcon.Mode.Selected))
        title = QLabel(tr(name))
        title.setObjectName("GroupTitle")
        subtitle = QLabel(tr(phrase))
        subtitle.setProperty("ofRole", "help")
        subtitle.setWordWrap(True)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(texts, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(2)
        layout.addLayout(head)
        layout.addSpacing(8)
        self.rows = [ToolRow(tool_id) for tool_id in tool_ids]
        for row in self.rows:
            layout.addWidget(row)
        if tool_ids == ["BatchPage"]:
            note = QLabel(tr(_AUTOMATE_NOTE))
            note.setProperty("ofRole", "help")
            note.setWordWrap(True)
            note.setContentsMargins(8, 6, 8, 0)
            layout.addWidget(note)
        layout.addStretch()


class ToolsCenter(QScrollArea):
    tool_requested = Signal(str)  # o id da ferramenta (ui.tools.TOOLS)
    quick_tools_requested = Signal(list)  # "Fixar na coluna rápida" / "Remover da coluna"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolsCenter")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.cards: dict[str, ToolRow] = {}
        self._build()

    # -- montagem ---------------------------------------------------------------------

    def _build(self):
        query = self.search.text() if hasattr(self, "search") else ""
        outer = QWidget()
        outer.setObjectName("toolsCenterContent")
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(40, 24, 40, 24)
        content = QWidget()
        content.setMaximumWidth(MAX_WIDTH)
        outer_layout.addStretch()
        outer_layout.addWidget(content, 100)
        outer_layout.addStretch()

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        title = QLabel(tr("Ferramentas"))
        title.setObjectName("HomeTitle")
        subtitle = QLabel(tr("Escolha pelo que você quer fazer. Cada grupo diz para que serve."))
        subtitle.setObjectName("pageSubtitle")
        self.search = QLineEdit(query)
        self.search.setObjectName("ToolSearch")
        self.search.setFixedSize(520, 44)
        self.search.setPlaceholderText(tr("O que você quer fazer? Ex.: assinar, cpf, word"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(build_search_icon(), QLineEdit.ActionPosition.LeadingPosition).setText(tr("Buscar"))
        self.search.setAccessibleName(tr("Buscar ferramenta"))
        self.search.textChanged.connect(self._apply_filter)
        self.search.returnPressed.connect(self._open_first)
        kbd = QLabel("Ctrl K")
        kbd.setObjectName("Kbd")
        kbd_layout = QHBoxLayout(self.search)
        kbd_layout.setContentsMargins(0, 0, 36, 0)
        kbd_layout.addStretch()
        kbd_layout.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)
        self._kbd = kbd
        heading = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        heading.addLayout(texts, 1)
        heading.addWidget(self.search, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(heading)

        # Mais usadas: pílulas, pelo uso real (as de fábrica completam).
        favorites = QHBoxLayout()
        favorites.setSpacing(8)
        favorites_label = QLabel(tr("Mais usadas"))
        favorites_label.setProperty("ofRole", "section")
        favorites.addWidget(favorites_label)
        favorites.addSpacing(4)
        self.favorites: list[QToolButton] = []
        for tool_id in most_used():
            pill = QToolButton()
            pill.setObjectName("FavoritePill")
            pill.setIcon(in_accent(getattr(sidebar_icons, TOOLS[tool_id].icon)()))
            pill.setIconSize(QSize(16, 16))
            pill.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            pill.setText(literal(tr(TOOLS[tool_id].title)))
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.clicked.connect(lambda _checked=False, t=tool_id: self.tool_requested.emit(t))
            favorites.addWidget(pill)
            self.favorites.append(pill)
        favorites.addStretch()
        layout.addLayout(favorites)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.groups: list[GroupCard] = []
        self.cards = {}
        for position, (name, phrase, tool_ids) in enumerate(GROUPS):
            card = GroupCard(name, phrase, tool_ids)
            grid.addWidget(card, position // COLUMNS, position % COLUMNS)
            self.groups.append(card)
            for row in card.rows:
                row.clicked.connect(lambda _checked=False, t=row.tool_id: self.tool_requested.emit(t))
                row.customContextMenuRequested.connect(lambda _pos, t=row.tool_id: self._row_menu(t))
                row.installEventFilter(self)
                self.cards[row.tool_id] = row
        for column in range(COLUMNS):
            grid.setColumnStretch(column, 1)
        for line in range(2):
            grid.setRowStretch(line, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        old = self.takeWidget()
        self.setWidget(outer)
        if old is not None:
            old.deleteLater()
        self.refresh_pins()
        self._apply_filter()

    def retranslate(self):
        self._build()

    def refresh_pins(self) -> None:
        quick = preferences().quick_tools()
        for tool_id, row in self.cards.items():
            row.set_pinned(tool_id in quick)

    def _row_menu(self, tool_id: str) -> None:
        quick = preferences().quick_tools()
        menu = QMenu(self)
        if tool_id in quick:
            action = menu.addAction(tr("Remover da coluna"))
            action.triggered.connect(lambda: self.quick_tools_requested.emit([t for t in quick if t != tool_id]))
        else:
            action = menu.addAction(tr("Fixar na coluna rápida"))
            action.triggered.connect(lambda: self.quick_tools_requested.emit([*quick, tool_id]))
        menu.exec(self.cursor().pos())

    # -- filtro -----------------------------------------------------------------------

    def _apply_filter(self, *_args):
        """Esconde as linhas que não batem e os grupos vazios; mostra o sinônimo que achou."""
        query = self.search.text()
        entries = {entry.tool.id: entry for entry in search_index.entries(with_modes=False)}
        for card in self.groups:
            shown = 0
            for row in card.rows:
                found, reason = search_index.match(entries[row.tool_id], query)
                row.setHidden(not found)
                row.set_reason(reason)
                shown += found
            card.setHidden(shown == 0)
        self._kbd.setVisible(not query)  # o "x" de limpar ocupa o lugar

    def visible_cards(self) -> list[ToolRow]:
        """As linhas à mostra, na ordem de leitura (grupo a grupo)."""
        return [row for card in self.groups if not card.isHidden() for row in card.rows if not row.isHidden()]

    def focus_search(self) -> None:
        """Ctrl+K nesta aba: o campo grande assume (a busca do topo some aqui)."""
        self.search.setFocus()
        self.search.selectAll()

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus()

    # -- teclado ----------------------------------------------------------------------

    def _open_first(self):
        visible = self.visible_cards()
        if visible:
            visible[0].click()

    def eventFilter(self, watched, event):
        # Para cima e para baixo andam pelas ferramentas à mostra, grupo a grupo.
        if isinstance(watched, ToolRow) and event.type() == QEvent.Type.KeyPress:
            step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(event.key())
            if step is not None:
                visible = self.visible_cards()
                target = visible.index(watched) + step if watched in visible else -1
                if 0 <= target < len(visible):
                    visible[target].setFocus()
                    self.ensureWidgetVisible(visible[target])
                return True
        return super().eventFilter(watched, event)
