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
        self.query_edit.returnPressed.connect(lambda: self.search_requested.emit(self.query_edit.text()))

        self.prev_button = QPushButton()
        self.prev_button.setIcon(build_prev_page_icon())
        self.prev_button.clicked.connect(self.prev_requested)

        self.next_button = QPushButton()
        self.next_button.setIcon(build_next_page_icon())
        self.next_button.clicked.connect(self.next_requested)

        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.closed)

        self.count_label = QLabel()
        self._count: tuple[int, int] | None = None
        self._searching = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.query_edit, 1)
        layout.addWidget(self.count_label)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.close_button)
        self.retranslate()

    def retranslate(self) -> None:
        self.query_edit.setPlaceholderText(tr("Buscar no documento..."))
        self.prev_button.setToolTip(tr("Ocorrência anterior"))
        self.next_button.setToolTip(tr("Próxima ocorrência"))
        self.close_button.setText(tr("Fechar"))
        self._update_count_label()

    def set_count(self, current: int, total: int, searching: bool = False) -> None:
        """`searching`: a busca ainda está percorrendo o documento (o total pode crescer)."""
        self._count = (current, total)
        self._searching = searching
        self._update_count_label()

    def clear_count(self) -> None:
        self._count = None
        self._searching = False
        self.count_label.setText("")

    def _update_count_label(self) -> None:
        if self._count is None:
            return
        current, total = self._count
        if total == 0:
            text = tr("Buscando...") if self._searching else tr("Nenhuma ocorrência")
        else:
            text = tr("{current} de {total}").format(current=current, total=total)
            if self._searching:
                text += "…"
        self.count_label.setText(text)

    def query(self) -> str:
        return self.query_edit.text()

    def focus_query(self) -> None:
        self.query_edit.setFocus()
        self.query_edit.selectAll()
