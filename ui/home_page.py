"""A aba Início: abrir um PDF, as ferramentas de partida e os arquivos recentes."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from ui import sidebar_icons
from ui.i18n import tr
from ui.icon import build_app_icon
from ui.tools import ROW_OF, SECTIONS
from ui.viewer.viewer_icons import build_open_icon

# Os atalhos de partida, ao lado de "Abrir PDF...": o que se faz sem ter um documento aberto.
_STARTERS = ["CreatePage", "MergePage", "ConvertPage", "CompressPage"]


class HomePage(QWidget):
    open_requested = Signal(str)  # o caminho; vazio para escolher o arquivo
    tool_requested = Signal(int)  # a linha em ui.tools.SECTIONS

    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self._preferences = preferences

        logo = QLabel()
        logo.setPixmap(build_app_icon().pixmap(56, 56))
        self._title = QLabel()
        self._title.setObjectName("pageTitle")
        self._subtitle = QLabel()
        self._subtitle.setObjectName("pageSubtitle")
        heading = QVBoxLayout()
        heading.addWidget(self._title)
        heading.addWidget(self._subtitle)
        top = QHBoxLayout()
        top.addWidget(logo)
        top.addSpacing(8)
        top.addLayout(heading, 1)

        self._open_button = QPushButton()
        self._open_button.setObjectName("primaryButton")
        self._open_button.setIcon(build_open_icon())
        self._open_button.clicked.connect(lambda: self.open_requested.emit(""))
        buttons = QHBoxLayout()
        buttons.addWidget(self._open_button)
        self._starter_buttons = []
        for class_name in _STARTERS:
            row = ROW_OF[class_name]
            button = QPushButton()
            button.setIcon(getattr(sidebar_icons, SECTIONS[row][0])())
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _checked=False, r=row: self.tool_requested.emit(r))
            buttons.addWidget(button)
            self._starter_buttons.append((button, row))
        buttons.addStretch()

        self._recent_title = QLabel()
        self._recent_title.setObjectName("sectionTitle")
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recentList")
        self.recent_list.itemActivated.connect(self._open_item)
        self.recent_list.itemClicked.connect(self._open_item)
        self._empty_label = QLabel()
        self._empty_label.setObjectName("pageSubtitle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 36, 48, 36)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addSpacing(12)
        layout.addLayout(buttons)
        layout.addSpacing(16)
        layout.addWidget(self._recent_title)
        layout.addWidget(self.recent_list, 1)
        layout.addWidget(self._empty_label)
        layout.addStretch(0)  # sem recentes (a lista some), o espaço sobra embaixo, não entre os itens
        self.retranslate()

    def retranslate(self):
        self._title.setText(tr("Bem-vindo ao OpenFolio PDF Suite"))
        self._subtitle.setText(tr("Abra um PDF para ler e trabalhar nele, ou comece por uma ferramenta."))
        self._open_button.setText(tr("Abrir PDF..."))
        for button, row in self._starter_buttons:
            button.setText(tr(SECTIONS[row][1]))
            button.setToolTip(tr(SECTIONS[row][2]))
        self._recent_title.setText(tr("Recentes"))
        self._empty_label.setText(tr("Os PDFs abertos aparecem aqui."))
        self.refresh()

    def refresh(self):
        """Relê a lista de recentes (a aba Início é mostrada de novo a cada visita)."""
        self.recent_list.clear()
        for path in self._preferences.recent_files():
            item = QListWidgetItem(f"{Path(path).name}    —    {Path(path).parent}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.recent_list.addItem(item)
        has_recent = self.recent_list.count() > 0
        self.recent_list.setVisible(has_recent)
        self._empty_label.setVisible(not has_recent)

    def _open_item(self, item: QListWidgetItem):
        self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole))
