"""As tarefas de todos os documentos num lugar só: o botão "N tarefas" da barra de status e o
popover com cada operação (em andamento, concluída, falhou ou cancelada).

Os gerenciadores continuam um por documento (ui/tasks.py); aqui fica só a visão agregada."""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
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
from ui.i18n import plural, tr
from ui.top_bar import BusySpinner
from ui.viewer.viewer_icons import build_check_circle_icon, build_close_icon, build_list_checks_icon, build_warning_circle_icon

if TYPE_CHECKING:
    from ui.tasks import TaskManager

RUNNING, DONE, FAILED, CANCELLED = "running", "ok", "error", "cancelled"
_STATE_TEXT = {RUNNING: "Em andamento", DONE: "Concluída", FAILED: "Falhou", CANCELLED: "Cancelada"}
WIDTH = 380
MARGIN = (8, 32)  # da direita e de baixo da janela


def ago(timestamp: float, now: float | None = None) -> str:
    """"agora", "há 2 min" ou "14:32": quando uma tarefa terminou."""
    seconds = (time.time() if now is None else now) - timestamp
    if seconds < 60:
        return tr("agora")
    if seconds < 3600:
        return tr("há {n} min").format(n=int(seconds // 60))
    return time.strftime("%H:%M", time.localtime(timestamp))


@dataclass
class TaskEntry:
    title: str
    document: str
    state: str = RUNNING
    done: int = 0
    total: int = 0
    message: str = ""  # o que a operação diz agora ("página 12 de 25")
    reason: str = ""  # por que falhou
    finished_at: float = 0.0
    manager: "TaskManager | None" = field(default=None, repr=False)


class TaskLog(QObject):
    """Registra o que os gerenciadores de tarefas dos documentos avisam."""

    changed = Signal()
    view_requested = Signal(object)  # o gerenciador da tarefa: a janela mostra o documento dele

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[TaskEntry] = []
        self._running: dict[int, TaskEntry] = {}  # id do gerenciador -> a tarefa dele em andamento
        self._reasons: dict[int, str] = {}

    def watch(self, manager, document_name) -> None:
        """`document_name()` dá o nome do documento na hora em que a tarefa começa."""
        key = id(manager)
        manager.started.connect(lambda title: self._started(key, title, document_name(), manager))
        manager.progress_changed.connect(lambda done, total, message: self._progress(key, done, total, message))
        manager.failed_with.connect(lambda reason: self._reasons.__setitem__(key, reason))
        manager.finished.connect(lambda outcome: self._finished(key, outcome))

    def _started(self, key: int, title: str, document: str, manager=None):
        entry = TaskEntry(title, document, manager=manager)
        self._running[key] = entry
        self.entries.insert(0, entry)
        self.changed.emit()

    def _progress(self, key: int, done: int, total: int, message: str = ""):
        entry = self._running.get(key)
        if entry is not None:
            entry.done, entry.total, entry.message = done, total, message
            self.changed.emit()

    def _finished(self, key: int, outcome: str):
        entry = self._running.pop(key, None)
        if entry is not None:
            entry.state = outcome if outcome in _STATE_TEXT else FAILED
            entry.reason = self._reasons.pop(key, "") if entry.state == FAILED else ""
            entry.finished_at = time.time()
            self.changed.emit()

    def running(self) -> int:
        return sum(entry.state == RUNNING for entry in self.entries)

    def clear_finished(self) -> None:
        self.entries = [entry for entry in self.entries if entry.state == RUNNING]
        self.changed.emit()


def _detail(entry: TaskEntry) -> str:
    """A segunda linha: o arquivo e o que se sabe do andamento ou do desfecho."""
    if entry.state == RUNNING:
        progress = entry.message or (tr("{done} de {total}").format(done=entry.done, total=entry.total) if entry.total else "")
        return " · ".join(part for part in (entry.document, progress) if part)
    if entry.state == FAILED:
        return " · ".join(part for part in (entry.document, entry.reason.splitlines()[0] if entry.reason else "") if part)
    if entry.state == CANCELLED:
        return f"{entry.document} · {tr('cancelada por você')}"
    return f"{entry.document} · {ago(entry.finished_at)}"


def _icon_mode(state: str) -> QIcon.Mode:
    """A cancelada fica apagada (text3)."""
    return QIcon.Mode.Disabled if state == CANCELLED else QIcon.Mode.Normal


class _TaskRow(QFrame):
    """Uma tarefa, pelo desfecho: em andamento (%, barra e Cancelar), concluída (✓ e Ver),
    falhou (fundo de erro e Ver motivo) ou cancelada (apagada)."""

    def __init__(self, entry: TaskEntry, log: TaskLog, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskRow")
        self.setProperty("state", entry.state)
        self.entry = entry
        t = theme.tokens()
        if entry.state == RUNNING:
            icon: QWidget = BusySpinner(16)
        else:
            icon = QLabel()
            if entry.state == DONE:
                state_icon = build_check_circle_icon(QColor(t["success"]))
            elif entry.state == FAILED:
                state_icon = build_warning_circle_icon(QColor(t["danger"]))
            else:
                state_icon = build_close_icon()
            icon.setPixmap(state_icon.pixmap(QSize(16, 16), _icon_mode(entry.state)))
        name = QLabel(entry.title)
        name.setObjectName("TaskName")
        name.setProperty("muted", entry.state == CANCELLED)
        self.detail = QLabel(_detail(entry))
        self.detail.setProperty("ofRole", "help")
        self.detail.setMinimumWidth(40)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(name)
        texts.addWidget(self.detail)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(texts, 1)
        self.action: QPushButton | None = None
        if entry.state == RUNNING:
            if entry.total:
                percent = QLabel(f"{round(100 * entry.done / entry.total)}%")
                percent.setObjectName("TaskPercent")
                top.addWidget(percent, 0, Qt.AlignmentFlag.AlignTop)
            self.action = QPushButton(tr("Cancelar"))
            self.action.clicked.connect(self._cancel)
        elif entry.state == DONE:
            self.action = QPushButton(tr("Ver"))
            self.action.clicked.connect(lambda: log.view_requested.emit(entry.manager))
        elif entry.state == FAILED and entry.reason:
            self.action = QPushButton(tr("Ver motivo"))
            self.action.setProperty("ofTone", "danger")
            self.action.clicked.connect(self._show_reason)
        if self.action is not None:
            self.action.setProperty("ofVariant", "ghost")
            self.action.setProperty("ofSize", "compact")
            top.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(top)
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
        self.reason = QLabel(entry.reason)
        self.reason.setWordWrap(True)
        self.reason.setProperty("ofRole", "help")
        self.reason.hide()
        layout.addWidget(self.reason)
        self.setAccessibleName(f"{entry.title}, {tr(_STATE_TEXT[entry.state])}, {_detail(entry)}")

    def _cancel(self):
        if self.entry.manager is not None:
            self.entry.manager.cancel()

    def _show_reason(self):
        self.reason.setVisible(not self.reason.isVisible())
        popover = self.window()
        if isinstance(popover, TaskPopover):
            popover.place()


class TaskPopover(QFrame):
    """Acima da barra de status, a 8 px da direita e a 32 px de baixo da janela."""

    hidden = Signal()

    def __init__(self, log: TaskLog, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("TaskPopover")
        self.setFixedWidth(WIDTH)
        self._log = log
        self._anchor: QWidget | None = None
        self.title = QLabel()
        self.title.setObjectName("TaskPopoverTitle")
        self.clear_button = QPushButton()
        self.clear_button.setProperty("ofVariant", "ghost")
        self.clear_button.setProperty("ofSize", "compact")
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
            self.rows.addWidget(_TaskRow(entry, self._log))
        if not self._log.entries:
            empty = QLabel(tr("As operações que você rodar aparecem aqui, com o andamento de cada uma."))
            empty.setProperty("ofRole", "help")
            empty.setWordWrap(True)
            self.rows.addWidget(empty)
        self.title.setText(tr("Tarefas"))
        self.clear_button.setText(tr("Limpar concluídas"))
        self.clear_button.setEnabled(any(entry.state != RUNNING for entry in self._log.entries))
        self.place()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.hidden.emit()

    def place(self) -> None:
        """Ancorado à janela do botão: 8 px da direita, 32 px de baixo."""
        self.adjustSize()
        if self._anchor is None:
            return
        window = self._anchor.window()
        corner = window.mapToGlobal(QPoint(window.width(), window.height()))
        self.move(corner.x() - MARGIN[0] - self.width(), corner.y() - MARGIN[1] - self.height())

    def show_above(self, button: QWidget):
        self._anchor = button
        self.refresh()
        self.show()


class TasksButton(QToolButton):
    """Na barra de status, só quando há tarefas: "1 tarefa em andamento" ou "1 em andamento ·
    3 concluídas". Abre o popover (e fica marcado enquanto ele está aberto)."""

    def __init__(self, log: TaskLog, parent=None):
        super().__init__(parent)
        self.setObjectName("TasksButton")
        self.setIcon(build_list_checks_icon("accent"))
        self.setIconSize(QSize(14, 14))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._log = log
        self.popover = TaskPopover(log, self)
        self.popover.hidden.connect(lambda: self.setChecked(False))
        self.clicked.connect(self._toggle)
        log.changed.connect(self.refresh)
        self.refresh()

    def _toggle(self):
        self.setChecked(True)
        self.popover.show_above(self)

    def refresh(self):
        running = self._log.running()
        done = sum(entry.state == DONE for entry in self._log.entries)
        failed = sum(entry.state == FAILED for entry in self._log.entries)
        parts = []
        if running:
            parts.append(plural(running, "1 em andamento", "{count} em andamento"))
        if done:
            parts.append(plural(done, "1 concluída", "{count} concluídas"))
        if failed:
            parts.append(plural(failed, "1 falhou", "{count} falharam"))
        if running and len(parts) == 1:
            text = plural(running, "1 tarefa em andamento", "{count} tarefas em andamento")
        else:
            text = " · ".join(parts) or plural(len(self._log.entries), "1 tarefa", "{count} tarefas")
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolTip(tr("Tarefas"))
        self.setVisible(bool(self._log.entries))
