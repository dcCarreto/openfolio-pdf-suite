"""Barra de busca de texto do visualizador."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ui.i18n import tr
from ui.viewer.viewer_icons import build_next_page_icon, build_prev_page_icon


class SearchBar(QWidget):
    """Campo de busca com navegação entre ocorrências e contador."""

    search_requested = Signal(str)
    next_requested = Signal()
    prev_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText(tr("Buscar no documento..."))
        self.query_edit.returnPressed.connect(lambda: self.search_requested.emit(self.query_edit.text()))

        prev_button = QPushButton()
        prev_button.setIcon(build_prev_page_icon())
        prev_button.setToolTip(tr("Ocorrência anterior"))
        prev_button.clicked.connect(self.prev_requested)

        next_button = QPushButton()
        next_button.setIcon(build_next_page_icon())
        next_button.setToolTip(tr("Próxima ocorrência"))
        next_button.clicked.connect(self.next_requested)

        close_button = QPushButton(tr("Fechar"))
        close_button.clicked.connect(self.closed)

        self.count_label = QLabel()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.query_edit, 1)
        layout.addWidget(self.count_label)
        layout.addWidget(prev_button)
        layout.addWidget(next_button)
        layout.addWidget(close_button)

    def set_count(self, current: int, total: int) -> None:
        if total == 0:
            self.count_label.setText(tr("Nenhuma ocorrência"))
        else:
            self.count_label.setText(tr("{current} de {total}").format(current=current, total=total))

    def query(self) -> str:
        return self.query_edit.text()

    def focus_query(self) -> None:
        self.query_edit.setFocus()
        self.query_edit.selectAll()
