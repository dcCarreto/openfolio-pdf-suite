"""Uma instância só do app (ui/instances.py) e uma operação por vez em cada janela (ui/tasks.py)."""

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.instances import AppWindows, InstanceServer, send_to_running_instance
from ui.tasks import run_task, task_manager, wait_for_tasks

ROOT = Path(__file__).resolve().parent.parent
# O segundo processo, como num duplo clique. No mesmo processo não daria: o pipe do Windows só
# entrega com o servidor lendo ao mesmo tempo. Com "--bruto", manda antes uma mensagem que não
# é uma lista de caminhos.
_SECOND_PROCESS = """
import sys
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket
from ui.instances import send_to_running_instance
app = QCoreApplication([])
name, args = sys.argv[1], sys.argv[2:]
if args[:1] == ["--bruto"]:
    args = args[1:]
    socket = QLocalSocket()
    socket.connectToServer(name)
    socket.waitForConnected(1000)
    socket.write(b'{"comando": "apagar"}')
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
print(send_to_running_instance(args, name=name))
"""


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _name():
    return f"openfolio-teste-{uuid.uuid4().hex}"  # nenhum teste conversa com o app aberto


def _second_process(name, *args):
    return subprocess.Popen([sys.executable, "-c", _SECOND_PROCESS, name, *args],
                            cwd=ROOT, stdout=subprocess.PIPE, text=True)


def _until(condition, app):
    for _ in range(3000):
        app.processEvents()
        if condition():
            return True
        threading.Event().wait(0.01)
    return False


def test_without_a_running_instance_nothing_is_sent(app):
    assert send_to_running_instance(["x.pdf"], name=_name()) is False


def test_the_running_instance_receives_only_the_existing_pdfs(app, make_pdf, tmp_path):
    pdf = str(make_pdf("contrato.pdf", [(200, 200)]))
    (tmp_path / "notas.txt").write_text("x")
    received = []
    name = _name()
    # Filho do app: se o coletor de lixo do Python o apagasse no meio dos eventos de outro
    # teste, o processo caía (no app, ele vive até o fim do main).
    server = InstanceServer(received.append, name=name, parent=app)
    assert server.is_listening()

    sender = _second_process(name, pdf, str(tmp_path / "notas.txt"), "--debug")

    assert _until(lambda: received, app)
    assert sender.communicate(timeout=30)[0].strip() == "True"
    assert received == [[os.path.abspath(pdf)]]


def test_a_message_that_is_not_a_list_of_paths_is_ignored(app, make_pdf):
    pdf = str(make_pdf("contrato.pdf", [(200, 200)]))
    received = []
    name = _name()
    _server = InstanceServer(received.append, name=name, parent=app)

    sender = _second_process(name, "--bruto", pdf)

    assert _until(lambda: received, app)
    assert sender.communicate(timeout=30)[0].strip() == "True"
    assert received == [[os.path.abspath(pdf)]]  # só a mensagem válida, que veio depois


def test_each_pdf_opens_in_a_new_window_unless_one_is_empty(app, make_pdf, tmp_path):
    from ui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    windows = AppWindows(lambda: MainWindow(settings=settings))
    first, second = (str(make_pdf(f"{n}.pdf", [(200, 200)])) for n in ("um", "dois"))
    try:
        windows.open([])  # o app abrindo sem arquivo
        windows.open([first])  # vai para a janela vazia
        windows.open([second])

        opened = windows.windows()
        assert [w.session.path() for w in opened] == [first, second]
        assert opened[1].pos() != opened[0].pos()

        # Uma operação numa janela não trava a outra.
        release = threading.Event()
        assert run_task(opened[0].sidebar, "Lenta", lambda _progress: release.wait(5))
        assert task_manager(opened[0].sidebar).is_busy()
        assert not task_manager(opened[1].sidebar).is_busy()
        release.set()
        assert wait_for_tasks()
    finally:
        for window in windows.windows():
            window.close()
