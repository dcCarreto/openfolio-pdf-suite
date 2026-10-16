"""Execução das operações fora da thread da interface.

Antes, cada botão chamava `core.*.run()` direto no handler: OCR, redação, comparação visual
ou o LibreOffice deixavam a janela "Não está respondendo", sem progresso nem como cancelar.

Agora as abas entregam a operação a `run_task`, que a executa numa thread de trabalho:

- Uma operação por vez no app inteiro. Duas operações gravando ao mesmo tempo (ou uma
  alterando o arquivo que a outra lê) não fazem sentido para o usuário, e assim o painel
  de ferramentas fica desabilitado enquanto uma roda (ver `MainWindow`).
- O andamento chega pelo `Progress` de `core/progress.py`; "Cancelar" o sinaliza, e a
  operação para no próximo ponto seguro sem gravar nada (as gravações são atômicas).
- Os resultados e erros voltam para a thread da interface por sinais: `on_success` e
  `on_error` sempre rodam nela, podendo mexer em widgets e abrir diálogos.
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from core.base import EncryptedPDFError
from core.progress import OperationCancelled, Progress
from ui.i18n import tr

logger = logging.getLogger(__name__)

# Erros esperados (entrada inválida, PDF protegido, cancelamento): a mensagem basta, sem
# rastro de pilha no log.
_EXPECTED_ERRORS = (ValueError, EncryptedPDFError, OperationCancelled, FileNotFoundError, PermissionError)


class _Signals(QObject):
    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[Progress], Any], progress: Progress, signals: _Signals):
        super().__init__()
        self.setAutoDelete(True)
        self._fn = fn
        self._progress = progress
        self._signals = signals

    def run(self):
        try:
            result = self._fn(self._progress)
        except BaseException as exc:  # noqa: BLE001 — tudo volta para a interface
            self._signals.failed.emit(exc)
        else:
            self._signals.succeeded.emit(result)


class TaskManager(QObject):
    """Roda uma operação por vez numa thread de trabalho e informa o andamento."""

    started = Signal(str)  # título da operação
    progress_changed = Signal(int, int, str)  # feito, total (0 = sem medida), mensagem
    finished = Signal(str)  # "ok", "error" ou "cancelled"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._busy = False
        self._title = ""
        self._progress: Progress | None = None
        self._signals: _Signals | None = None
        self._on_success: Callable[[Any], None] | None = None
        self._on_error: Callable[[BaseException], None] | None = None

    def is_busy(self) -> bool:
        return self._busy

    def title(self) -> str:
        return self._title

    def start(
        self,
        title: str,
        fn: Callable[[Progress], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> bool:
        """Inicia `fn(progress)` numa thread de trabalho. Devolve False (sem rodar nada) se
        já houver uma operação em andamento."""
        if self._busy:
            return False
        self._busy = True
        self._title = title
        self._on_success = on_success
        self._on_error = on_error

        signals = _Signals()
        signals.progress.connect(self.progress_changed)
        signals.succeeded.connect(self._handle_success)
        signals.failed.connect(self._handle_failure)
        self._signals = signals  # mantém o objeto vivo enquanto a thread o usa

        cancel_event = threading.Event()
        self._progress = Progress(callback=signals.progress.emit, cancel_event=cancel_event)
        logger.info("Iniciando: %s", title)
        self.started.emit(title)
        self._pool.start(_Job(fn, self._progress, signals))
        return True

    def cancel(self) -> None:
        if self._busy and self._progress is not None:
            logger.info("Cancelamento pedido: %s", self._title)
            self._progress.cancel()

    def wait(self, timeout_ms: int = 60_000) -> bool:
        """Processa eventos até a operação atual terminar (usado ao fechar a janela e nos
        testes). Devolve False se o tempo acabar antes."""
        if not self._busy:
            return True
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        self.finished.disconnect(loop.quit)
        QCoreApplication.processEvents()
        return not self._busy

    def _handle_success(self, result):
        callback = self._on_success
        self._finish("ok")
        logger.info("Concluído: %s", self._title)
        if callback is not None:
            callback(result)

    def _handle_failure(self, exc: BaseException):
        callback = self._on_error
        if isinstance(exc, OperationCancelled):
            logger.info("Cancelado: %s", self._title)
            self._finish("cancelled")
            return
        if isinstance(exc, _EXPECTED_ERRORS):
            logger.info("Falhou: %s: %s", self._title, exc)
        else:
            logger.error("Falhou: %s", self._title, exc_info=(type(exc), exc, exc.__traceback__))
        self._finish("error")
        if callback is not None:
            callback(exc)

    def _finish(self, outcome: str):
        self._busy = False
        self._progress = None
        self._on_success = None
        self._on_error = None
        self.finished.emit(outcome)


_manager: TaskManager | None = None


def task_manager() -> TaskManager:
    """O gerenciador único do app (criado na primeira chamada, na thread da interface)."""
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager


def call(fn: Callable[..., Any], *args, **kwargs) -> Callable[[Progress], Any]:
    """Tarefa que chama `fn(*args, **kwargs)`.

    Os argumentos são avaliados aqui, na thread da interface: valores de widgets não podem
    ser lidos de dentro da thread de trabalho.
    """
    return lambda _progress: fn(*args, **kwargs)


def call_with_progress(fn: Callable[..., Any], *args, **kwargs) -> Callable[[Progress], Any]:
    """Como `call`, para operações que aceitam `progress=` (andamento e cancelamento)."""
    return lambda progress: fn(*args, progress=progress, **kwargs)


def run_task(
    parent: QWidget,
    title: str,
    fn: Callable[[Progress], Any],
    on_success: Callable[[Any], None] | None = None,
    error_message: str | None = None,
    on_error: Callable[[BaseException], None] | None = None,
) -> bool:
    """Roda `fn(progress)` fora da thread da interface, no padrão das abas.

    Em caso de erro, mostra `error_message` (já traduzida, com `{error}`) num diálogo, a
    menos que `on_error` trate o erro. Cancelamentos não mostram diálogo: a barra de status
    já informa.
    """
    manager = task_manager()
    if manager.is_busy():
        QMessageBox.information(
            parent,
            title,
            tr('Aguarde "{task}" terminar, ou cancele essa operação.').format(task=manager.title()),
        )
        return False

    def handle_error(exc: BaseException):
        if on_error is not None:
            on_error(exc)
            return
        template = error_message or tr("Falha ao processar: {error}")
        QMessageBox.critical(parent, title, template.format(error=exc))

    return manager.start(title, fn, on_success=on_success, on_error=handle_error)


def wait_for_tasks(timeout_ms: int = 60_000) -> bool:
    """Espera a operação em andamento terminar (testes e fechamento da janela)."""
    return task_manager().wait(timeout_ms)
