"""Barra de busca de texto do visualizador."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ui.i18n import tr
from ui.viewer.viewer_icons import build_next_page_icon, build_prev_page_icon


class SearchBar(QWidget):
    """Campo de busca com navegação entre ocorrências e contador. Enter busca; de novo, com o
    mesmo termo, vai à próxima ocorrência (Shift+Enter, à anterior) e Esc fecha a barra."""

    search_requested = Signal(str)
    next_requested = Signal()
    prev_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.query_edit = QLineEdit()
        self.query_edit.returnPressed.connect(self._on_return)
        self.query_edit.textChanged.connect(self._forget_search)

        self.case_check = QCheckBox()
        self.word_check = QCheckBox()
        self.case_check.toggled.connect(self._search_again)
        self.word_check.toggled.connect(self._search_again)

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
        self._searched = False  # o texto do campo é o da busca mostrada

        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.query_edit, 1)
        layout.addWidget(self.case_check)
        layout.addWidget(self.word_check)
        layout.addWidget(self.count_label)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.close_button)
        self.retranslate()

    def retranslate(self) -> None:
        self.query_edit.setPlaceholderText(tr("Buscar no documento..."))
        self.case_check.setText(tr("Maiúsculas/minúsculas"))
        self.word_check.setText(tr("Palavra inteira"))
        self.prev_button.setToolTip(tr("Ocorrência anterior"))
        self.next_button.setToolTip(tr("Próxima ocorrência"))
        self.close_button.setText(tr("Fechar"))
        self._update_count_label()

    def _on_return(self) -> None:
        if not self._searched:
            self._search_again()
        elif QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.prev_requested.emit()
        else:
            self.next_requested.emit()

    def _search_again(self) -> None:
        self._searched = bool(self.query_edit.text().strip())
        if self._searched or self._count is not None:
            self.search_requested.emit(self.query_edit.text())

    def _forget_search(self) -> None:
        self._searched = False

    def match_case(self) -> bool:
        return self.case_check.isChecked()

    def whole_word(self) -> bool:
        return self.word_check.isChecked()

    def set_count(self, current: int, total: int, searching: bool = False) -> None:
        """`searching`: a busca ainda está percorrendo o documento (o total pode crescer)."""
        self._count = (current, total)
        self._searching = searching
        self._update_count_label()

    def clear_count(self) -> None:
        self._count = None
        self._searching = False
        self._searched = False
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

    def set_query(self, text: str) -> None:
        self.query_edit.setText(text)

    def focus_query(self) -> None:
        self.query_edit.setFocus()
        self.query_edit.selectAll()
