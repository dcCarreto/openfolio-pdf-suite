"""Progresso e cancelamento das operações longas, e acesso serializado ao pdfium.

As operações rodam fora da thread da interface (ver `ui/tasks.py`). Elas recebem um
`Progress` opcional: informam o andamento por ele e, nos pontos seguros (antes de cada
página, antes de gravar), checam se o usuário cancelou. Como toda gravação é atômica
(`core.base.atomic_output`), cancelar nunca deixa um arquivo pela metade.

O pdfium não é thread-safe: duas threads não podem chamá-lo ao mesmo tempo, nem com
documentos diferentes. O visualizador e as operações compartilham `PDFIUM_LOCK`, e as
operações o seguram só durante o trecho de pdfium de cada página — o visualizador espera no
máximo o render de uma página, nunca a operação inteira.
"""

import threading
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


class _PdfiumLock:
    """Um RLock que, ao fechar o app, para de admitir quem chega (`close`).

    Ao sair, o pypdfium2 fecha os documentos e destrói a biblioteca sem lock (ver
    `core.base`), e para isso o app precisa segurar este lock. Mas um RLock não tem fila: uma
    thread que o solta e logo o pega de novo (renders seguidos, uma operação página a página)
    pode passar na frente de quem espera indefinidamente. Do Python 3.10 ao 3.13 a saída
    esperava assim até desistir, e o pdfium era destruído com a thread dentro dele. Depois de
    `close`, quem já está dentro termina (e pode reentrar), e quem chega espera para sempre:
    na saída só sobram threads daemon, que o Python descarta."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._depth = threading.local()
        self._closing = False

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        depth = getattr(self._depth, "count", 0)
        if self._closing and depth == 0:
            if blocking:
                threading.Event().wait(None if timeout < 0 else timeout)
            return False
        if not self._lock.acquire(blocking, timeout):
            return False
        self._depth.count = depth + 1
        return True

    def release(self) -> None:
        self._lock.release()
        self._depth.count -= 1

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *exc_info) -> None:
        self.release()

    def close(self, timeout: float) -> bool:
        """Fecha a entrada e espera (até `timeout`) quem está dentro sair; fica com o lock."""
        self._closing = True
        if not self._lock.acquire(timeout=timeout):
            return False
        self._depth.count = getattr(self._depth, "count", 0) + 1
        return True


PDFIUM_LOCK = _PdfiumLock()


class OperationCancelled(Exception):
    """O usuário cancelou a operação; nada foi gravado."""

    def __init__(self, message: str = "Operação cancelada."):
        super().__init__(message)


class Progress:
    """Canal entre uma operação e quem a executa.

    `callback(done, total, message)` recebe o andamento (`total == 0` quando não dá para
    medir). `cancel_event`, quando sinalizado, faz a próxima checagem levantar
    `OperationCancelled`.
    """

    def __init__(
        self,
        callback: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ):
        self._callback = callback
        self._cancel_event = cancel_event or threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def check(self) -> None:
        if self._cancel_event.is_set():
            raise OperationCancelled()

    def silent(self) -> "Progress":
        """Mesmo cancelamento, sem informar andamento: para cada arquivo de um lote, cujo
        andamento é o do lote."""
        return Progress(cancel_event=self._cancel_event)

    def update(self, done: int, total: int, message: str = "") -> None:
        self.check()
        if self._callback is not None:
            self._callback(done, total, message)

    def steps(self, items: Iterable[T], total: int | None = None, message: str = "") -> Iterator[T]:
        """Percorre `items` informando o andamento e checando o cancelamento antes de cada um."""
        if total is None:
            items = list(items)
            total = len(items)
        for done, item in enumerate(items):
            self.update(done, total, message)
            yield item
        self.update(total, total, message)


def ensure_progress(progress: Progress | None) -> Progress:
    """O `Progress` recebido, ou um que não informa nada a ninguém (uso direto de `core/`)."""
    return progress if progress is not None else Progress()
