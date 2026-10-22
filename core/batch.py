"""Processamento em lote (A05): a mesma operação aplicada a vários PDFs, um de cada vez.

Um arquivo que falha não interrompe o lote: o erro fica no resultado dele e o próximo
segue. Cancelar interrompe na hora (o arquivo em andamento não é gravado, como em qualquer
operação) e os já processados ficam na pasta de saída.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .progress import OperationCancelled, Progress, ensure_progress

# operação(entrada, saída, progresso): o progresso só serve para checar o cancelamento.
FileOperation = Callable[[str, str, Progress], object]


@dataclass
class BatchFileResult:
    input_path: str
    output_path: str = ""  # vazio se falhou
    error: BaseException | None = None


def pdfs_in_folder(folder: str) -> list[str]:
    """Os PDFs da pasta (sem subpastas), em ordem alfabética."""
    return sorted(
        (str(path) for path in Path(folder).iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=str.lower,
    )


class BatchProcess:
    def run(
        self,
        input_paths: list[str],
        output_dir: str,
        operation: FileOperation,
        suffix: str,
        progress: Progress | None = None,
    ) -> list[BatchFileResult]:
        progress = ensure_progress(progress)
        if not input_paths:
            raise ValueError("Nenhum PDF para processar.")
        os.makedirs(output_dir, exist_ok=True)
        # Nunca grava por cima de um arquivo que já existe (nem de uma entrada).
        used = {name.lower() for name in os.listdir(output_dir)}
        results = []
        for input_path in progress.steps(input_paths, message="Processando os arquivos"):
            stem = Path(input_path).stem
            name, counter = f"{stem}_{suffix}.pdf", 2
            while name.lower() in used:  # o Windows não diferencia maiúsculas
                name, counter = f"{stem}_{suffix} ({counter}).pdf", counter + 1
            used.add(name.lower())
            output_path = os.path.join(output_dir, name)
            try:
                operation(input_path, output_path, progress.silent())
            except OperationCancelled:
                raise
            except Exception as exc:
                results.append(BatchFileResult(input_path, error=exc))
                continue
            results.append(BatchFileResult(input_path, output_path))
        return results
