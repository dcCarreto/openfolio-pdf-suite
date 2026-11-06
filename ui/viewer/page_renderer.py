"""Renderização de páginas fora da thread da interface, e o cache das imagens prontas.

Antes, toda página (a da tela, as da rolagem contínua e as miniaturas) era renderizada na
thread da interface: num escaneado ou numa planta, cada página leva de 50 a 300 ms, e a
janela parava esse tempo a cada página nova — ao rolar, ao dar zoom, ao abrir o documento
(as miniaturas). Agora:

- `PageRenderer` tem uma thread própria que renderiza os pedidos por ordem de prioridade
  (a página à vista antes das vizinhas, as vizinhas antes das miniaturas). Pedido que deixou
  de interessar (o usuário já rolou para longe) é retirado da fila antes de custar nada.
- O resultado é um QImage (que pode nascer fora da thread da interface) entregue por sinal;
  quem pediu o converte em QPixmap.
- `PixmapCache` guarda as páginas prontas até um limite de memória: voltar a uma página,
  redesenhar marcações por cima dela ou trocar a ocorrência da busca não renderiza de novo.

O pdfium não é thread-safe: a thread segura `PDFIUM_LOCK` só durante o render de uma página.
Trocar ou fechar o documento (`set_document`) acontece com o lock seguro, e a thread confere
a geração do documento com o lock seguro antes de usá-lo: um documento fechado nunca é lido.
"""

import itertools
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from core.geometry import PageGeometry
from core.progress import PDFIUM_LOCK
from ui.thread_relay import ensure_relay, post
from ui.viewer.render import render_image

logger = logging.getLogger(__name__)

# Prioridades (menor sai antes).
VISIBLE = 0  # à vista
NEARBY = 1  # logo acima/abaixo, ou a próxima página: prontas antes de o usuário chegar
THUMBNAIL = 2

Key = tuple  # ("page", página, escala, ...) ou ("thumb", página)

_IDLE_SECONDS = 10.0  # a thread termina sozinha depois disso sem pedidos


class _Job:
    __slots__ = ("key", "page", "scale", "ratio", "rotation", "fit_width", "fit_longest")

    def __init__(self, key, page, scale, ratio, rotation, fit_width, fit_longest):
        self.key = key
        self.page = page
        self.scale = scale
        self.ratio = ratio
        self.rotation = rotation
        self.fit_width = fit_width
        self.fit_longest = fit_longest


class PageRenderer(QObject):
    """Fila de renders de um documento pdfium, atendida por uma thread de trabalho.

    `rendered` chega na thread da interface; `accept` diz se o resultado ainda é do
    documento atual.
    """

    # Chave do pedido, QImage e (segundos que levou, geometria da página): quem pediu aprende
    # quanto o documento custa e ganha a geometria sem abrir a página de novo.
    rendered = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_relay()
        self._cond = threading.Condition()
        self._document = None
        self._generation = 0
        self._jobs: dict[Key, tuple[int, int, _Job]] = {}
        self._order = itertools.count()
        self._thread: threading.Thread | None = None
        self._stopped = False
        self._rendering = False

    # -- documento ---------------------------------------------------------------

    def set_document(self, document) -> None:
        """Troca o documento (ou None). Chame com `PDFIUM_LOCK` seguro antes de fechar o
        anterior: a partir daqui a thread não o toca mais, e o que ela já entregou dele é
        descartado."""
        with PDFIUM_LOCK, self._cond:
            self._document = document
            self._generation += 1
            self._jobs.clear()

    def stop(self) -> None:
        """Para a thread (o dono vai embora). Pedidos novos voltam a iniciá-la."""
        with self._cond:
            self._jobs.clear()
            self._stopped = True
            self._cond.notify_all()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._thread = None

    # -- pedidos -----------------------------------------------------------------

    def request(
        self,
        key: Key,
        page: int,
        scale: float,
        ratio: float,
        rotation: int = 0,
        priority: int = VISIBLE,
        fit_width: float | None = None,
        fit_longest: float | None = None,
    ) -> None:
        """Pede o render de `page`. Um pedido com a mesma chave só muda de prioridade.

        `fit_width` / `fit_longest`: em vez de `scale`, a escala que deixa a página com essa
        largura (ou o lado maior com esse tamanho) em pixels lógicos — miniaturas —, calculada
        pela thread com a página já aberta."""
        with self._cond:
            if self._document is None:
                return
            current = self._jobs.get(key)
            if current is not None and current[0] <= priority:
                return
            order = current[1] if current is not None else next(self._order)
            self._jobs[key] = (priority, order, _Job(key, page, scale, ratio, rotation, fit_width, fit_longest))
            self._stopped = False
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="openfolio-render", daemon=True)
                self._thread.start()
            self._cond.notify()

    def retain(self, keep: Callable[[Key], bool]) -> None:
        """Tira da fila os pedidos para os quais `keep(chave)` é falso."""
        with self._cond:
            for key in [key for key in self._jobs if not keep(key)]:
                del self._jobs[key]

    def cancel(self, keys: Iterable[Key]) -> None:
        with self._cond:
            for key in keys:
                self._jobs.pop(key, None)

    def pending(self) -> int:
        with self._cond:
            return len(self._jobs)

    def is_pending(self, key: Key) -> bool:
        with self._cond:
            return key in self._jobs

    def is_idle(self) -> bool:
        """Nada na fila nem sendo renderizado (o resultado pode ainda estar a caminho)."""
        with self._cond:
            return not self._jobs and not self._rendering

    # -- thread de trabalho --------------------------------------------------------

    def _next_job(self) -> tuple[_Job, int] | None:
        with self._cond:
            while not self._jobs and not self._stopped:
                if not self._cond.wait(timeout=_IDLE_SECONDS) and not self._jobs:
                    self._thread = None  # parada por ociosidade: o próximo pedido inicia outra
                    return None
            if self._stopped:
                return None
            key = min(self._jobs, key=lambda k: self._jobs[k][:2])
            _priority, _order, job = self._jobs.pop(key)
            self._rendering = True
            return job, self._generation

    def _run(self) -> None:
        while True:
            next_job = self._next_job()
            if next_job is None:
                return
            job, generation = next_job
            try:
                result = self._render(job, generation)
            except Exception:  # a página fica sem imagem; as outras seguem
                logger.debug("Falha ao renderizar a página %s", job.page, exc_info=True)
                result = None
            if result is not None:  # chega só se o dono ainda existir (ver `ui.thread_relay`)
                post(self, "rendered", (generation, job.key), *result)
            with self._cond:
                self._rendering = False
            time.sleep(0)  # a thread da interface pega o lock do pdfium, se estiver esperando

    def _render(self, job: _Job, generation: int) -> tuple[QImage, tuple[float, PageGeometry]] | None:
        with PDFIUM_LOCK:
            with self._cond:
                document = self._document if generation == self._generation else None
            if document is None:
                return None
            started = time.perf_counter()
            page = document[job.page]
            try:
                geometry = PageGeometry.from_pdfium_page(page)
                scale = job.scale
                if job.fit_width is not None:
                    width = page.get_height() if job.rotation in (90, 270) else page.get_width()
                    scale = job.fit_width / width if width > 0 else job.scale
                elif job.fit_longest is not None:
                    longest = max(page.get_size())
                    scale = job.fit_longest / longest if longest > 0 else job.scale
                image = render_image(page, scale, job.ratio, rotation=job.rotation)
            finally:
                page.close()
            return image, (time.perf_counter() - started, geometry)

    # -- resultados (thread da interface) ----------------------------------------------

    def accept(self, tagged_key) -> Key | None:
        """A chave de um resultado de `rendered`, ou None se ele for de um documento que já
        saiu (descartar)."""
        generation, key = tagged_key
        return key if generation == self._generation else None


class PixmapCache:
    """Páginas renderizadas, as mais recentes primeiro, até `budget` bytes."""

    def __init__(self, budget: int = 192 * 1024 * 1024):
        self._budget = budget
        self._items: OrderedDict[Key, QPixmap] = OrderedDict()
        self._bytes = 0

    @staticmethod
    def _size(pixmap: QPixmap) -> int:
        return pixmap.width() * pixmap.height() * max(1, pixmap.depth() // 8)

    def get(self, key: Key) -> QPixmap | None:
        pixmap = self._items.get(key)
        if pixmap is not None:
            self._items.move_to_end(key)
        return pixmap

    def put(self, key: Key, pixmap: QPixmap) -> None:
        old = self._items.pop(key, None)
        if old is not None:
            self._bytes -= self._size(old)
        self._items[key] = pixmap
        self._bytes += self._size(pixmap)
        while self._bytes > self._budget and len(self._items) > 1:
            _key, dropped = self._items.popitem(last=False)
            self._bytes -= self._size(dropped)

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0

    def __contains__(self, key: Key) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)
