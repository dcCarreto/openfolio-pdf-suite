"""Andamento da operação em execução, na barra de status: título, etapa, barra e "Cancelar"."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QWidget

from ui.i18n import tr
from ui.tasks import TaskManager


class TaskStatus(QWidget):
    """Fica oculto sem operação em andamento. Sem total conhecido, a barra fica ocupada
    (animação contínua) em vez de parada em 0%."""

    def __init__(self, manager: TaskManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._title = ""

        self.label = QLabel()
        self.bar = QProgressBar()
        self.bar.setFixedWidth(180)
        self.bar.setTextVisible(False)
        self.cancel_button = QPushButton(tr("Cancelar"))
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cancel_button.clicked.connect(self._cancel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(self.cancel_button)

        manager.started.connect(self._on_started)
        manager.progress_changed.connect(self._on_progress)
        manager.finished.connect(self._on_finished)
        self.setVisible(manager.is_busy())

    def _on_started(self, title: str):
        self._title = title
        self.label.setText(title)
        self.bar.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText(tr("Cancelar"))
        self.show()

    def _on_progress(self, done: int, total: int, message: str):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
        else:
            self.bar.setRange(0, 0)
        step = tr(message) if message else ""
        if total > 0 and step:
            step = f"{step} ({min(done + 1, total)}/{total})"
        self.label.setText(f"{self._title} — {step}" if step else self._title)

    def _on_finished(self, _outcome: str):
        self.hide()

    def retranslate(self):
        if self.cancel_button.isEnabled():
            self.cancel_button.setText(tr("Cancelar"))

    def _cancel(self):
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText(tr("Cancelando..."))
        self._manager.cancel()
