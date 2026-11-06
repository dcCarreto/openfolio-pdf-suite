"""Resultados das threads de trabalho entregues na thread da interface, com segurança.

As threads (render das páginas, detalhes do documento, miniaturas dos recentes) trabalham
para um QObject da interface, filho de uma aba ou da tela Início. Emitir um sinal desse objeto
a partir da thread é inseguro: fechada a aba, o objeto é destruído na thread da interface
enquanto a thread de trabalho ainda o usa, e o processo cai (segfault), em vez de levantar um
RuntimeError que daria para tratar.

`post` emite, em vez disso, um sinal de um objeto que existe enquanto o app existir; ele chega
na thread da interface, e lá o sinal do dono só é emitido se o dono ainda existir. A destruição
de objetos da interface também acontece nessa thread, então entre conferir e emitir nada muda.
"""

import shiboken6
from PySide6.QtCore import QObject, Signal, Slot


class _Relay(QObject):
    deliver = Signal(object, str, object)  # dono, nome do sinal, argumentos

    def __init__(self) -> None:
        super().__init__()
        self.deliver.connect(self._deliver)

    @Slot(object, str, object)
    def _deliver(self, owner: QObject, signal_name: str, args: tuple) -> None:
        if shiboken6.isValid(owner):
            getattr(owner, signal_name).emit(*args)


_relay: _Relay | None = None


def ensure_relay() -> None:
    """Cria o mensageiro na thread da interface (chamar no construtor de quem vai usar
    `post`): criado numa thread de trabalho, ele viveria nela, e as entregas não chegariam."""
    global _relay
    if _relay is None:
        _relay = _Relay()


def post(owner: QObject, signal_name: str, *args) -> None:
    """Emite `owner.<signal_name>(*args)` na thread da interface, se `owner` ainda existir
    quando a entrega chegar. Seguro de chamar de qualquer thread."""
    assert _relay is not None, "ensure_relay() não foi chamado na thread da interface"
    _relay.deliver.emit(owner, signal_name, args)
