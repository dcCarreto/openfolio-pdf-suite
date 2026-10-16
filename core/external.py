"""Programas externos opcionais (LibreOffice, Ghostscript, Tesseract): localizar e rodar.

O app nunca instala nada: usa o programa se ele estiver no PATH ou numa pasta de instalação
comum, e as ferramentas explicam o que fazer quando não está.
"""

import shutil
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

from .messages import Message
from .progress import OperationCancelled, Progress

_POLL_INTERVAL = 0.2  # segundos entre checagens de cancelamento


def find_program(candidates: Iterable[str]) -> str | None:
    """O primeiro candidato que existe: um nome no PATH ou um caminho completo."""
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if Path(candidate).is_file():
            return candidate
    return None


_GHOSTSCRIPT_CANDIDATES = ["gswin64c", "gswin32c", "gs"]


def find_ghostscript() -> str | None:
    """Procura o executável do Ghostscript no PATH e na pasta padrão do Windows."""
    found = find_program(_GHOSTSCRIPT_CANDIDATES)
    if found:
        return found
    for root in (r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"):
        for exe in sorted(Path(root).glob("gs*/bin/gswin*c.exe"), reverse=True):
            return str(exe)
    return None


def run_cancellable(
    command: list[str],
    progress: Progress,
    timeout: float,
    program: str = "O programa externo",
    capture_stdout: bool = False,
) -> tuple[int, bytes]:
    """Roda `command` e espera o fim checando o cancelamento; encerra o processo se o
    usuário cancelar ou se passar do `timeout`. Devolve o código de saída e o stderr (ou o
    stdout, com `capture_stdout`, para programas que escrevem o resultado nele)."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL if capture_stdout else subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=_POLL_INTERVAL)
                return process.returncode, (stdout if capture_stdout else stderr) or b""
            except subprocess.TimeoutExpired:
                pass
            if progress.cancelled:
                raise OperationCancelled()
            if time.monotonic() > deadline:
                raise RuntimeError(
                    Message(
                        "{program} demorou demais para terminar (timeout de {seconds}s).",
                        program=Message(program),
                        seconds=round(timeout),
                    )
                )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
