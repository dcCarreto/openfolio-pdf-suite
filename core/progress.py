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

PDFIUM_LOCK = threading.RLock()


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
