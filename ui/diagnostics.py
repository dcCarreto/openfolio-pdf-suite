"""Log em arquivo e tratamento global de exceções.

No executável distribuído não há console (`console=False`): um erro fora dos `try` das abas
sumia sem deixar rastro, e não havia arquivo de log para anexar a uma issue. Agora:

- tudo o que passa pelo `logging` (início, fim e falha das operações, por exemplo) vai para
  `openfolio.log` na pasta de dados do app, com rotação para não crescer sem limite;
- uma exceção não tratada, na thread da interface ou em outra, é registrada com o rastro
  completo e mostrada num diálogo que diz onde está o log.
"""

import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.i18n import tr

logger = logging.getLogger("openfolio")

_LOG_FILE_NAME = "openfolio.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 3
_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"

_log_path: Path | None = None


def log_directory() -> Path:
    """Pasta de dados do app (ex.: %LOCALAPPDATA%/OpenFolio/OpenFolio PDF Suite/logs)."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return Path(base or Path.home() / ".openfolio") / "logs"


def log_path() -> Path | None:
    return _log_path


def setup_logging(directory: Path | None = None, level: int = logging.INFO) -> Path | None:
    """Liga o log em arquivo (e no console, quando há um). Devolve o caminho do arquivo, ou
    None se não foi possível criá-lo (o app funciona do mesmo jeito)."""
    global _log_path
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)

    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.WARNING)
        root.addHandler(console)

    directory = directory or log_directory()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _LOG_FILE_NAME
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
    except OSError:
        logger.warning("Não foi possível criar o arquivo de log em %s", directory, exc_info=True)
        return None
    handler.setFormatter(formatter)
    root.addHandler(handler)
    _log_path = path
    return path


class _ErrorReporter(QObject):
    """Leva o aviso de erro para a thread da interface (diálogos só podem ser abertos nela)."""

    report = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.report.connect(self._show)
        self._showing = False

    def _show(self, summary: str, details: str):
        if self._showing or QApplication.instance() is None:
            return  # um erro em cascata não abre uma pilha de diálogos
        self._showing = True
        try:
            box = QMessageBox(QApplication.activeWindow())
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle(tr("Erro inesperado"))
            text = tr("Ocorreu um erro inesperado: {error}").format(error=summary)
            if _log_path is not None:
                text += "\n\n" + tr("Os detalhes foram gravados em:\n{path}").format(path=_log_path)
            box.setText(text)
            box.setDetailedText(details)
            box.exec()
        finally:
            self._showing = False


_reporter: _ErrorReporter | None = None


def _handle(exc_type, exc_value, exc_traceback, thread_name: str | None = None) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    where = f" (thread {thread_name})" if thread_name else ""
    logger.critical("Exceção não tratada%s", where, exc_info=(exc_type, exc_value, exc_traceback))
    if _reporter is not None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        _reporter.report.emit(f"{exc_type.__name__}: {exc_value}", details)


def install_exception_hooks() -> None:
    """Instala os ganchos de `sys` e `threading`. Chamar depois de criar o QApplication."""
    global _reporter
    _reporter = _ErrorReporter()
    sys.excepthook = _handle

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        name = args.thread.name if args.thread is not None else None
        _handle(args.exc_type, args.exc_value, args.exc_traceback, name)

    threading.excepthook = thread_hook
