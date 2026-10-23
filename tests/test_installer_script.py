"""O instalador do Windows (packaging/windows/installer.iss) nunca abre o app como administrador."""

import re
from pathlib import Path

ISS = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "installer.iss"


def test_the_app_is_never_opened_elevated():
    # O instalador roda elevado (instalação para todos os usuários). Uma entrada [Run] sem
    # "postinstall" herda isso, a menos que tenha "runasoriginaluser": foi o caso da que reabre o
    # app depois de uma atualização, que o deixava rodando como administrador.
    run = ISS.read_text(encoding="utf-8").split("[Run]", 1)[1].split("\n[", 1)[0]
    opens_app = [line for line in run.splitlines() if re.match(r'Filename: "\{app\}\\\{#AppExeName\}"', line)]
    assert len(opens_app) == 2  # o "Abrir o OpenFolio" do assistente e o da atualização
    for line in opens_app:
        flags = re.search(r"Flags: ([^;]*)", line).group(1).split()
        assert "postinstall" in flags or "runasoriginaluser" in flags, line
