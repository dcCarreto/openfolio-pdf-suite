"""As tarefas de todos os documentos num lugar só: o botão "N tarefas" da barra de status e o
popover com cada operação (em andamento, concluída, falhou ou cancelada).

Os gerenciadores continuam um por documento (ui/tasks.py); aqui fica só a visão agregada."""

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.i18n import tr
from ui.top_bar import BusySpinner
from ui.viewer.viewer_icons import build_check_circle_icon, build_close_icon, build_list_checks_icon, build_warning_circle_icon

RUNNING, DONE, FAILED, CANCELLED = "running", "ok", "error", "cancelled"
_STATE_TEXT = {RUNNING: "Em andamento", DONE: "Concluída", FAILED: "Falhou", CANCELLED: "Cancelada"}


@dataclass
class TaskEntry:
    title: str
    document: str
    state: str = RUNNING
    done: int = 0
    total: int = 0


class TaskLog(QObject):
    """Registra o que os gerenciadores de tarefas dos documentos avisam."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[TaskEntry] = []
        self._running: dict[int, TaskEntry] = {}  # id do gerenciador -> a tarefa dele em andamento

    def watch(self, manager, document_name) -> None:
        """`document_name()` dá o nome do documento na hora em que a tarefa começa."""
        key = id(manager)
        manager.started.connect(lambda title: self._started(key, title, document_name()))
        manager.progress_changed.connect(lambda done, total, _message: self._progress(key, done, total))
        manager.finished.connect(lambda outcome: self._finished(key, outcome))

    def _started(self, key: int, title: str, document: str):
        entry = TaskEntry(title, document)
        self._running[key] = entry
        self.entries.insert(0, entry)
        self.changed.emit()

    def _progress(self, key: int, done: int, total: int):
        entry = self._running.get(key)
        if entry is not None:
            entry.done, entry.total = done, total
            self.changed.emit()

    def _finished(self, key: int, outcome: str):
        entry = self._running.pop(key, None)
        if entry is not None:
            entry.state = outcome if outcome in _STATE_TEXT else FAILED
            self.changed.emit()

    def running(self) -> int:
        return sum(entry.state == RUNNING for entry in self.entries)

    def clear_finished(self) -> None:
        self.entries = [entry for entry in self.entries if entry.state == RUNNING]
        self.changed.emit()


class _TaskRow(QFrame):
    def __init__(self, entry: TaskEntry, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskRow")
        self.setProperty("running", entry.state == RUNNING)
        if entry.state == RUNNING:
            icon: QWidget = BusySpinner(16)
        else:
            icon = QLabel()
            t = theme.tokens()
            if entry.state == DONE:
                state_icon = build_check_circle_icon(QColor(t["success"]))
            elif entry.state == FAILED:
                state_icon = build_warning_circle_icon(QColor(t["danger"]))
            else:
                state_icon = build_close_icon()
            icon.setPixmap(state_icon.pixmap(QSize(16, 16)))
        name = QLabel(entry.title)
        name.setObjectName("TaskName")
        state = QLabel(tr(_STATE_TEXT[entry.state]))
        state.setProperty("ofRole", "secondary")
        document = QLabel(entry.document)
        document.setProperty("ofRole", "secondary")
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(icon)
        top.addWidget(name, 1)
        top.addWidget(state)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addWidget(document)
        if entry.state == RUNNING:
            bar = QProgressBar()
            bar.setObjectName("TaskProgress")
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            if entry.total > 0:
                bar.setRange(0, entry.total)
                bar.setValue(entry.done)
            else:
                bar.setRange(0, 0)
            layout.addWidget(bar)
        self.setAccessibleName(f"{entry.title}, {tr(_STATE_TEXT[entry.state])}, {entry.document}")


class TaskPopover(QFrame):
    """Acima do botão "N tarefas", alinhado à direita dele."""

    def __init__(self, log: TaskLog, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("TaskPopover")
        self.setFixedWidth(360)
        self._log = log
        self.title = QLabel()
        self.title.setObjectName("TaskPopoverTitle")
        self.clear_button = QPushButton()
        self.clear_button.setProperty("ofVariant", "ghost")
        self.clear_button.clicked.connect(log.clear_finished)
        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(self.clear_button)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addLayout(self.rows)
        self.setGraphicsEffect(theme.floating_shadow(self))
        log.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        for entry in self._log.entries:
            self.rows.addWidget(_TaskRow(entry))
        if not self._log.entries:
            empty = QLabel(tr("Nenhuma tarefa."))
            empty.setProperty("ofRole", "secondary")
            self.rows.addWidget(empty)
        self.title.setText(tr("Tarefas"))
        self.clear_button.setText(tr("Limpar concluídas"))
        self.clear_button.setEnabled(any(entry.state != RUNNING for entry in self._log.entries))
        self.adjustSize()

    def show_above(self, button: QWidget):
        self.refresh()
        corner = button.mapToGlobal(QPoint(button.width(), 0))
        self.move(corner.x() - self.width(), corner.y() - self.height() - 6)
        self.show()


class TasksButton(QToolButton):
    """"N tarefas" na barra de status, enquanto alguma operação roda; abre o popover."""

    def __init__(self, log: TaskLog, parent=None):
        super().__init__(parent)
        self.setObjectName("TasksButton")
        self.setIcon(build_list_checks_icon())
        self.setIconSize(QSize(14, 14))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log = log
        self.popover = TaskPopover(log, self)
        self.clicked.connect(lambda: self.popover.show_above(self))
        log.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        running = self._log.running()
        text = tr("{count} tarefas").format(count=running) if running != 1 else tr("1 tarefa")
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolTip(tr("Tarefas"))
        self.setVisible(running > 0)
