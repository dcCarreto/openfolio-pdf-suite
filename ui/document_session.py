"""Estado compartilhado do documento aberto: o arquivo do usuário e o documento de trabalho.

Antes, cada ferramenta gravava num arquivo novo escolhido a cada operação, e o visualizador
passava a mostrar esse arquivo: depois de três operações havia três arquivos intermediários
na pasta do usuário, nenhum jeito de voltar atrás, e o "documento aberto" já não era o que
ele tinha aberto.

Agora o documento aberto é um documento de trabalho:

- `source_path()` é o arquivo do usuário; `path()` é a versão atual, que o visualizador
  mostra e as ferramentas leem. Ao abrir, as duas são o mesmo arquivo — nada é copiado.
- As ferramentas que alteram o documento gravam numa versão nova (`new_version_path()`,
  na pasta temporária da sessão) e chamam `open()` com ela, como faziam com o arquivo de
  saída: a sessão reconhece a própria versão e a empilha no histórico, em vez de abrir
  outro documento. Cada versão é um passo de desfazer/refazer.
- `save()` grava a versão atual por cima do arquivo do usuário (de forma atômica);
  `save_as()` grava em outro arquivo, que passa a ser o arquivo do documento.
- Enquanto houver alterações não salvas (`is_modified()`), abrir outro documento ou fechar
  a janela pergunta antes (`set_discard_confirmation`).

As versões temporárias ficam numa pasta própria por documento, apagada ao abrir outro
documento ou ao fechar o app.
"""

import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.base import atomic_output, forget_password, known_password, remember_password


@dataclass
class _Version:
    path: str
    label: str  # operação que gerou esta versão ("" para o arquivo aberto)


class DocumentSession(QObject):
    """Guarda o documento aberto (e o histórico de versões dele) e notifica quem depende.

    Uma única instância vive em MainWindow e é compartilhada pelo visualizador e por
    todos os painéis de ferramenta: abrir um arquivo em qualquer lugar do app atualiza
    o visualizador e todas as ferramentas ao mesmo tempo.
    """

    path_changed = Signal()
    history_changed = Signal()  # desfazer/refazer, versão nova ou documento salvo
    page_selection_changed = Signal()  # páginas selecionadas nas miniaturas
    current_page_changed = Signal()  # a página que o visualizador mostra

    def __init__(self):
        super().__init__()
        self._source: str | None = None
        self._versions: list[_Version] = []
        self._index = -1
        self._saved_index = -1
        self._work_dir: str | None = None
        self._pending: set[str] = set()
        self._counter = 0
        self._operation_label = ""
        self._confirm_discard = None
        self._last_change = "document"  # "document" (outro arquivo) ou "version"
        self._selected_pages: list[int] = []
        self._current_page = 0

    # -- consulta ---------------------------------------------------------------

    def path(self) -> str | None:
        """A versão atual do documento (o que o visualizador mostra e as ferramentas leem)."""
        return self._versions[self._index].path if self._versions else None

    def source_path(self) -> str | None:
        """O arquivo do usuário, onde "Salvar" grava."""
        return self._source

    def last_change(self) -> str:
        """"version" se a última troca foi uma versão do mesmo documento (operação,
        desfazer, refazer): o visualizador mantém a página em que estava."""
        return self._last_change

    def is_modified(self) -> bool:
        return bool(self._versions) and self._index != self._saved_index

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return 0 <= self._index < len(self._versions) - 1

    def undo_label(self) -> str:
        return self._versions[self._index].label if self.can_undo() else ""

    def redo_label(self) -> str:
        return self._versions[self._index + 1].label if self.can_redo() else ""

    def current_page(self) -> int:
        """A página (a partir de 0) que o visualizador está mostrando."""
        return self._current_page

    def set_current_page(self, index: int) -> None:
        if max(0, index) != self._current_page:
            self._current_page = max(0, index)
            self.current_page_changed.emit()

    def selected_pages(self) -> list[int]:
        """Páginas (a partir de 0) selecionadas nas miniaturas do visualizador."""
        return list(self._selected_pages)

    def set_selected_pages(self, pages: list[int]) -> None:
        pages = sorted(set(pages))
        if pages != self._selected_pages:
            self._selected_pages = pages
            self.page_selection_changed.emit()

    def is_version_path(self, path: str | None) -> bool:
        return bool(path and _key(path) in {_key(p) for p in self._pending})

    # -- abrir e versões ----------------------------------------------------------

    def set_discard_confirmation(self, callback) -> None:
        """`callback()` -> True para seguir (alterações salvas ou descartadas), False para
        cancelar. Chamado antes de trocar um documento com alterações não salvas."""
        self._confirm_discard = callback

    def note_operation(self, label: str) -> None:
        """Nome da operação em andamento, usado no "Desfazer <operação>" da versão que ela
        gerar (a janela liga isso ao início de cada operação)."""
        self._operation_label = label

    def new_version_path(self) -> str:
        """Caminho para uma versão nova do documento aberto. Uma ferramenta grava nele e
        depois chama `open()` com ele; até lá, nada muda."""
        if self._work_dir is None:
            self._work_dir = tempfile.mkdtemp(prefix="openfolio-doc-")
        self._counter += 1
        stem = Path(self._source).stem if self._source else "documento"
        path = os.path.join(self._work_dir, f"{stem}~{self._counter}.pdf")
        self._pending.add(path)
        return path

    def open(self, path: str) -> bool:
        """Abre `path`. Se for uma versão criada por `new_version_path()`, ela vira o passo
        seguinte do histórico do documento aberto; senão, abre outro documento (perguntando
        antes, se houver alterações não salvas). Devolve False se o usuário cancelar."""
        if self.is_version_path(path) and self._versions:
            del self._versions[self._index + 1 :]  # um passo novo apaga o "refazer"
            if self._saved_index > self._index:
                self._saved_index = -2  # a versão salva saiu do histórico
            self._versions.append(_Version(path=path, label=self._operation_label))
            self._index = len(self._versions) - 1
            password = known_password(self._source) if self._source else None
            if password:
                remember_password(path, password)
            self._changed("version")
            return True

        if not self._confirm_leave():
            return False
        self._reset()
        self._selected_pages = []
        self._current_page = 0
        self._source = path
        self._versions = [_Version(path=path, label="")]
        self._index = 0
        self._saved_index = 0
        self._changed("document")
        return True

    def clear(self) -> bool:
        if not self._confirm_leave():
            return False
        self._reset()
        self._changed("document")
        return True

    def undo(self) -> None:
        if self.can_undo():
            self._index -= 1
            self._changed("version")

    def redo(self) -> None:
        if self.can_redo():
            self._index += 1
            self._changed("version")

    # -- salvar -----------------------------------------------------------------

    def save(self) -> None:
        """Grava a versão atual no arquivo do usuário."""
        if not self._versions or self._source is None:
            return
        current = self.path()
        assert current is not None  # há versões
        if _key(current) != _key(self._source):
            _copy_atomically(current, self._source)
        self._saved_index = self._index
        self.history_changed.emit()

    def save_as(self, path: str) -> None:
        """Grava a versão atual em `path`, que passa a ser o arquivo do documento."""
        if not self._versions:
            return
        current = self.path()
        assert current is not None  # há versões
        if _key(current) != _key(path):
            _copy_atomically(current, path)
        password = known_password(current)
        if password:
            remember_password(path, password)
        self._source = path
        self._saved_index = self._index
        self.history_changed.emit()

    def discard_temporary_files(self) -> None:
        """Apaga as versões temporárias (ao fechar o app)."""
        self._remove_work_dir()

    # -- interno ----------------------------------------------------------------

    def _confirm_leave(self) -> bool:
        if not self.is_modified() or self._confirm_discard is None:
            return True
        return bool(self._confirm_discard())

    def _reset(self) -> None:
        # A senha digitada para abrir o documento sai da memória junto com ele (M32).
        for path in [self._source, *(version.path for version in self._versions)]:
            if path is not None:
                forget_password(path)
        self._remove_work_dir()
        self._source = None
        self._versions = []
        self._index = -1
        self._saved_index = -1
        self._pending = set()

    def _remove_work_dir(self) -> None:
        if self._work_dir is not None:
            # No Windows o visualizador pode estar com a versão atual aberta; o que não der
            # para apagar agora fica na pasta temporária do sistema.
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None

    def _changed(self, kind: str) -> None:
        self._last_change = kind
        self._operation_label = ""
        self.path_changed.emit()
        self.history_changed.emit()


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _copy_atomically(source: str, target: str) -> None:
    with atomic_output(target) as temp_path:
        shutil.copyfile(source, temp_path)
    with contextlib.suppress(OSError):
        os.utime(target)
