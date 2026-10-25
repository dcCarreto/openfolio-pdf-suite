"""A aba Ferramentas: busca (com sinônimos), filtro por categoria e todas as ferramentas em
cartões, numa grade que se ajusta à largura."""

import re

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionToolButton,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import sidebar_icons
from ui.i18n import tr
from ui.shortcuts import fold_text
from ui.tools import CATEGORIES, QUICK_TOOLS, ROW_OF, SECTIONS, SYNONYMS
from ui.viewer.viewer_icons import build_pin_icon, build_search_icon
from ui.widgets.flow_layout import FlowLayout

CARD_WIDTH = 250  # a largura mínima de um cartão: daí sai o número de colunas
CARD_GAP = 8
MAX_WIDTH = 1160


def columns_for(width: int) -> int:
    return max(1, (width + CARD_GAP) // (CARD_WIDTH + CARD_GAP))


class ToolCard(QToolButton):
    """Ícone num quadrado, nome, descrição e o alfinete das que estão no trilho rápido. O texto
    do botão é o nome da ferramenta (leitor de tela, testes); quem o desenha são os rótulos."""

    def __init__(self, row: int, parent=None, compact: bool = False):
        super().__init__(parent)
        icon, _title, _subtitle, _module, class_name = SECTIONS[row]
        self.row = row
        self._compact = compact  # os atalhos do Início: mais estreitos, ícone na cor do acento
        self.setObjectName("ShortcutCard" if compact else "ToolCard")
        self.setProperty("ofRole", "card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        tile = QLabel()
        tile.setObjectName("ShortcutIconTile" if compact else "ToolIconTile")
        size = 36 if compact else 34
        tile.setFixedSize(size, size)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode = QIcon.Mode.Selected if compact else QIcon.Mode.Normal
        self.setIcon(getattr(sidebar_icons, icon)())  # quem desenha é o quadrado; o ícone fica no botão
        tile.setPixmap(self.icon().pixmap(QSize(18, 18), mode))
        self.name_label = QLabel()
        self.name_label.setObjectName("ToolCardName")
        self.description_label = QLabel()
        self.description_label.setProperty("ofRole", "secondary")
        self.description_label.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.name_label)
        text.addWidget(self.description_label)
        text.addStretch()  # o nome alinha com o ícone, no topo
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*((14, 12, 14, 12) if compact else (12, 10, 12, 10)))
        layout.setSpacing(10)
        layout.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        self.pinned = class_name in QUICK_TOOLS and not compact
        self._pin = None
        if self.pinned:
            self._pin = QLabel()
            self._pin.setPixmap(build_pin_icon().pixmap(QSize(13, 13), QIcon.Mode.Disabled))
            layout.addWidget(self._pin, 0, Qt.AlignmentFlag.AlignTop)
        for label in self.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.retranslate()

    def retranslate(self):
        _icon, title, subtitle, _module, _class = SECTIONS[self.row]
        self.setText(tr(title))
        self.setToolTip(tr(subtitle))
        self.setAccessibleDescription(tr(subtitle))
        self.name_label.setText(tr(title))
        self.description_label.setText(tr(subtitle))
        if self._pin is not None:
            self._pin.setToolTip(tr("No trilho rápido"))

    def sizeHint(self) -> QSize:
        layout = self.layout()
        hint = layout.sizeHint() if layout is not None else QSize()
        return hint.expandedTo(self.minimumSizeHint())

    def minimumSizeHint(self) -> QSize:
        return QSize(150 if self._compact else CARD_WIDTH, 56)

    def paintEvent(self, event):
        # Só o fundo e a borda do cartão (QSS): o conteúdo são os rótulos.
        painter = QStylePainter(self)
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text = ""
        option.icon = QIcon()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)


class ToolsCenter(QScrollArea):
    tool_requested = Signal(int)  # a linha em ui.tools.SECTIONS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolsCenter")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.cards: dict[int, ToolCard] = {}
        self._category: int | None = None  # índice em CATEGORIES, ou None (todas)
        self._columns = 0
        self._build()

    # -- montagem ---------------------------------------------------------------------

    def _build(self):
        query = self.search.text() if hasattr(self, "search") else ""
        outer = QWidget()
        outer.setObjectName("toolsCenterContent")
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(40, 40, 40, 40)
        content = QWidget()
        content.setMaximumWidth(MAX_WIDTH)
        outer_layout.addStretch()
        outer_layout.addWidget(content, 100)
        outer_layout.addStretch()
        self._content = content

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        title = QLabel(tr("Ferramentas"))
        title.setObjectName("pageTitle")
        subtitle = QLabel(tr("Tudo o que o OpenFolio faz com um PDF, por categoria."))
        subtitle.setObjectName("pageSubtitle")
        self.search = QLineEdit(query)
        self.search.setObjectName("ToolSearch")
        self.search.setFixedSize(340, 36)
        self.search.setPlaceholderText(tr("Buscar ferramenta (ex.: assinar, cpf, word)"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(build_search_icon(), QLineEdit.ActionPosition.LeadingPosition).setText(tr("Buscar"))
        self.search.setAccessibleName(tr("Buscar ferramenta"))
        self.search.textChanged.connect(self._apply_filter)
        self.search.returnPressed.connect(self._open_first)
        heading = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        heading.addLayout(texts, 1)
        heading.addWidget(self.search, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(heading)

        # Filtro por categoria: "Todas" e as categorias, com a contagem.
        chips = QWidget()
        chips_layout = FlowLayout(chips, spacing=8)
        self.chips: list[QToolButton] = []
        self._chip_group = QButtonGroup(self)
        entries = [(tr("Todas"), len(SECTIONS))] + [(tr(name), len(names)) for name, names in CATEGORIES]
        for index, (name, count) in enumerate(entries):
            chip = QToolButton()
            chip.setProperty("ofRole", "chip")
            chip.setCheckable(True)
            chip.setText(f"{name}  {count}")
            chip.setAccessibleName(f"{name}, {count}")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, i=index: self.set_category(None if i == 0 else i - 1))
            self._chip_group.addButton(chip)
            chips_layout.addWidget(chip)
            self.chips.append(chip)
        layout.addWidget(chips)

        self.cards = {}
        self._groups: list[tuple[QLabel, QGridLayout, list[ToolCard]]] = []
        for name, class_names in CATEGORIES:
            heading_label = QLabel(tr(name))
            heading_label.setObjectName("ToolGroupTitle")
            grid = QGridLayout()
            grid.setHorizontalSpacing(CARD_GAP)
            grid.setVerticalSpacing(CARD_GAP)
            cards = []
            for class_name in class_names:
                card = ToolCard(ROW_OF[class_name])
                card.clicked.connect(lambda _checked=False, r=card.row: self.tool_requested.emit(r))
                card.installEventFilter(self)
                self.cards[card.row] = card
                cards.append(card)
            layout.addSpacing(8)
            layout.addWidget(heading_label)
            layout.addLayout(grid)
            self._groups.append((heading_label, grid, cards))
        layout.addStretch(1)  # sobra embaixo, e não nos cartões

        old = self.takeWidget()
        self.setWidget(outer)
        if old is not None:
            old.deleteLater()
        self._columns = 0
        self.chips[0 if self._category is None else self._category + 1].setChecked(True)
        self._apply_filter()

    def retranslate(self):
        self._build()

    # -- filtro -----------------------------------------------------------------------

    def set_category(self, category: int | None) -> None:
        self._category = category
        self.chips[0 if category is None else category + 1].setChecked(True)
        self._apply_filter()

    def matches(self, row: int, query: str) -> bool:
        """Nome, descrição ou sinônimo: cada palavra digitada precisa ser o começo de uma
        palavra deles ("word" acha Converter, não o "password" de Proteger)."""
        _icon, title, subtitle, _module, class_name = SECTIONS[row]
        words = re.findall(r"\w+", fold_text(f"{tr(title)} {tr(subtitle)} {title} {SYNONYMS.get(class_name, '')}"))
        return all(any(word.startswith(typed) for word in words) for typed in re.findall(r"\w+", fold_text(query)))

    def visible_cards(self) -> list[ToolCard]:
        """Os cartões à mostra, na ordem da tela."""
        return [card for _label, _grid, cards in self._groups for card in cards if not card.isHidden()]

    def _apply_filter(self, *_args):
        query = self.search.text()
        for index, (label, _grid, cards) in enumerate(self._groups):
            in_category = self._category is None or self._category == index
            shown = 0
            for card in cards:
                visible = in_category and self.matches(card.row, query)
                card.setHidden(not visible)
                shown += visible
            label.setHidden(shown == 0)
        self._columns = 0  # refaz a grade com os que sobraram
        self._layout_grids()

    def _layout_grids(self):
        # Pela área visível (o conteúdo ainda pode estar com a largura antiga num resize).
        width = min(MAX_WIDTH, self.viewport().width() - 80)
        columns = columns_for(width)
        if columns == self._columns:
            return
        self._columns = columns
        for _label, grid, cards in self._groups:
            for card in cards:
                grid.removeWidget(card)
            visible = [card for card in cards if not card.isHidden()]
            for position, card in enumerate(visible):
                grid.addWidget(card, position // columns, position % columns)
            # Todas as colunas com o mesmo peso, também as vazias: um grupo com menos cartões
            # que colunas não estica os que tem.
            for column in range(max(columns, grid.columnCount())):
                grid.setColumnStretch(column, 1 if column < columns else 0)
                grid.setColumnMinimumWidth(column, CARD_WIDTH if column < columns else 0)

    def columns(self) -> int:
        return self._columns

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_grids()

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_grids()
        self.search.setFocus()

    # -- teclado ----------------------------------------------------------------------

    def _open_first(self):
        visible = self.visible_cards()
        if visible:
            visible[0].click()

    def eventFilter(self, watched, event):
        # As setas andam entre os cartões, como numa grade.
        if isinstance(watched, ToolCard) and event.type() == QEvent.Type.KeyPress:
            steps = {
                Qt.Key.Key_Left: -1,
                Qt.Key.Key_Right: 1,
                Qt.Key.Key_Up: -max(1, self._columns),
                Qt.Key.Key_Down: max(1, self._columns),
            }
            step = steps.get(event.key())
            if step is not None:
                visible = self.visible_cards()
                if watched in visible:
                    target = visible.index(watched) + step
                    if 0 <= target < len(visible):
                        visible[target].setFocus()
                        self.ensureWidgetVisible(visible[target])
                return True
        return super().eventFilter(watched, event)
