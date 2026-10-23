"""Uma instância só do app por usuário.

Antes, com o OpenFolio já aberto, um duplo clique em outro PDF abria outro processo. Agora o
segundo processo entrega os arquivos ao que já está aberto (por um `QLocalServer`, só do
usuário) e sai; o primeiro abre cada um numa janela nova, como antes para quem vê, mas sem
carregar o app de novo.
"""

import getpass
import json
import sys

from PySide6.QtCore import QObject, QPoint
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ui.app_events import pdf_paths_from_arguments

SERVER_NAME = f"openfolio-pdf-suite-{getpass.getuser()}"
_MAX_MESSAGE = 1 << 20  # caminhos de arquivo, não mais que isso


def send_to_running_instance(paths: list[str], name: str = SERVER_NAME) -> bool:
    """Entrega `paths` à instância aberta. Devolve False se não houver nenhuma."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    # Sem instância aberta a conexão falha na hora; os 5 s só contam quando há uma ocupada,
    # e esperar por ela é melhor que abrir um segundo app (com 1 s, um CI carregado desistia).
    if not socket.waitForConnected(5000):
        return False
    if sys.platform == "win32":
        # Deixa a instância aberta trazer a janela nova para a frente: o Windows só permite
        # isso a quem o usuário acabou de usar, e esse é este processo.
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    # Sem laço de eventos aqui (o processo sai logo depois): espera os dados saírem.
    if socket.write(json.dumps(paths).encode("utf-8")) == -1:
        return False
    while socket.bytesToWrite() and socket.waitForBytesWritten(1000):
        pass
    if socket.bytesToWrite():
        return False
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(1000)
    return True


class InstanceServer(QObject):
    """Recebe os arquivos que outros processos do app entregam e os passa a `open_paths`."""

    def __init__(self, open_paths, name: str = SERVER_NAME, parent=None):
        super().__init__(parent)
        self._open_paths = open_paths
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(name):
            # No Linux e no macOS, o socket de uma execução que caiu fica no disco: ninguém
            # respondeu em send_to_running_instance, então ele é dessa execução.
            QLocalServer.removeServer(name)
            self._server.listen(name)
        self._server.newConnection.connect(self._accept)

    def is_listening(self) -> bool:
        return self._server.isListening()

    def _accept(self):
        while (socket := self._server.nextPendingConnection()) is not None:
            received = bytearray()

            def read(socket=socket, received=received):
                received.extend(socket.readAll().data())
                if len(received) > _MAX_MESSAGE:
                    socket.abort()

            def done(socket=socket, received=received, read=read):
                read()
                socket.deleteLater()
                if len(received) > _MAX_MESSAGE:
                    return
                try:
                    arguments = json.loads(received.decode("utf-8"))
                except ValueError:
                    return
                if isinstance(arguments, list) and all(isinstance(a, str) for a in arguments):
                    # De outro processo do usuário, mas valida como a linha de comando.
                    self._open_paths(pdf_paths_from_arguments(arguments))

            socket.readyRead.connect(read)
            socket.disconnected.connect(done)


class AppWindows:
    """As janelas abertas do app: cada PDF que chega de fora abre numa janela nova, a não
    ser que haja uma sem documento (a que acabou de abrir, por exemplo)."""

    def __init__(self, make_window):
        self._make_window = make_window
        self._windows: list = []

    def windows(self) -> list:
        return list(self._windows)

    def open(self, paths: list[str]) -> None:
        """Abre cada PDF numa janela; sem nenhum (o app aberto de novo), uma janela vazia."""
        targets: list[str | None] = [*paths] or [None]
        for path in targets:
            window = self._window_for()
            if path is not None:
                window.session.open(path)
            window.show()
            window.raise_()
            window.activateWindow()

    def _window_for(self):
        empty = next((w for w in reversed(self._windows) if w.session.path() is None), None)
        if empty is not None:
            return empty
        window = self._make_window()
        if self._windows:  # a nova não fica exatamente em cima da anterior
            window.move(self._windows[-1].pos() + QPoint(30, 30))
        self._windows.append(window)
        window.destroyed.connect(lambda _obj=None, w=window: self._windows.remove(w))
        return window
