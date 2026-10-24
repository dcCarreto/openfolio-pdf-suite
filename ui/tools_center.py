"""A aba Ferramentas: todas as ferramentas, por categoria, cada uma num cartão."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

from ui import sidebar_icons
from ui.i18n import tr
from ui.tools import CATEGORIES, ROW_OF, SECTIONS

_COLUMNS = 6


class ToolsCenter(QScrollArea):
    tool_requested = Signal(int)  # a linha em ui.tools.SECTIONS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolsCenter")
        self.setWidgetResizable(True)
        self.cards: dict[int, QToolButton] = {}
        self._build()

    def _build(self):
        content = QWidget()
        content.setObjectName("toolsCenterContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(10)
        title = QLabel(tr("Todas as ferramentas"))
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.cards = {}
        for category, class_names in CATEGORIES:
            heading = QLabel(tr(category))
            heading.setObjectName("sectionTitle")
            layout.addSpacing(8)
            layout.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(10)
            grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
            for index, class_name in enumerate(class_names):
                row = ROW_OF[class_name]
                card = self._card(row)
                grid.addWidget(card, index // _COLUMNS, index % _COLUMNS)
                self.cards[row] = card
            layout.addLayout(grid)
        layout.addStretch()
        old = self.takeWidget()
        self.setWidget(content)
        if old is not None:
            old.deleteLater()

    def _card(self, row: int) -> QToolButton:
        icon, title, subtitle = SECTIONS[row][0], SECTIONS[row][1], SECTIONS[row][2]
        card = QToolButton()
        card.setObjectName("toolCard")
        card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        card.setIcon(getattr(sidebar_icons, icon)())
        card.setIconSize(QSize(32, 32))
        card.setText(tr(title))
        card.setToolTip(tr(subtitle))
        card.setFixedSize(QSize(150, 96))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.clicked.connect(lambda _checked=False, r=row: self.tool_requested.emit(r))
        return card

    def retranslate(self):
        self._build()
