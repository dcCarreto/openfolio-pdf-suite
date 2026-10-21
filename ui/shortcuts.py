"""Paleta de comandos (Ctrl+K) e atalhos de teclado configuráveis (A18).

Os dois diálogos recebem a lista de comandos da janela principal: pares (rótulo, QAction),
em que o `objectName` da ação é a chave estável usada nas preferências.
"""

import unicodedata

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.i18n import tr

# Teclas que o visualizador e as abas já usam (ui/viewer/pdf_viewer.py, compare_view.py,
# organize_page.py): um comando nelas tiraria a tecla de lá.
_RESERVED = (
    "Ctrl+F", "Ctrl+G", "Ctrl+C", "Ctrl+=", "Ctrl++", "Ctrl+-", "Ctrl+0",
    "PgDown", "PgUp", "Right", "Left", "Home", "End", "F3", "Shift+F3", "Del",
)

_NAVIGATION_KEYS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown)


def _fold(text: str) -> str:
    """Minúsculas sem acento, para "acoes" achar "Ações"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def _portable(sequence: QKeySequence) -> str:
    return sequence.toString(QKeySequence.SequenceFormat.PortableText)


class CommandPalette(QDialog):
    """Lista os comandos habilitados e filtra pelo que se digita (nome ou descrição da
    ferramenta); Enter ou duplo clique escolhe, e `chosen` fica com a ação."""

    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Paleta de comandos"))
        self.resize(560, 440)
        self.chosen = None

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Digite o nome de uma ferramenta ou comando"))
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.list)

        self._actions = []
        self._haystacks = []
        for label, action in commands:
            if not action.isEnabled():
                continue
            keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            self.list.addItem(QListWidgetItem(action.icon(), f"{label}    {keys}" if keys else label))
            self._actions.append(action)
            self._haystacks.append(_fold(f"{label} {action.statusTip()}"))

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run)
        self.list.itemActivated.connect(self._run)
        self._filter("")

    def _filter(self, text: str):
        words = _fold(text).split()
        first = -1
        for row, haystack in enumerate(self._haystacks):
            visible = all(word in haystack for word in words)
            self.list.item(row).setHidden(not visible)
            if visible and first < 0:
                first = row
        self.list.setCurrentRow(first)

    def eventFilter(self, watched, event):
        # Setas e PgUp/PgDn no campo de busca andam pela lista, sem tirar o foco do campo.
        if watched is self.search and event.type() == QEvent.Type.KeyPress and event.key() in _NAVIGATION_KEYS:
            QApplication.sendEvent(self.list, event)
            return True
        return super().eventFilter(watched, event)

    def _run(self, *_args):
        row = self.list.currentRow()
        if row >= 0 and not self.list.item(row).isHidden():
            self.chosen = self._actions[row]
            self.accept()


class ShortcutsDialog(QDialog):
    """Tabela comando × atalho. `defaults` guarda os atalhos de fábrica de cada comando
    (chave -> lista de QKeySequence), para restaurar e para saber o que mudou."""

    def __init__(self, commands, defaults, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Atalhos de teclado"))
        self.resize(600, 560)
        self._defaults = defaults

        self.table = QTableWidget(len(commands), 2)
        self.table.setHorizontalHeaderLabels([tr("Comando"), tr("Atalho")])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 200)
        self._rows = []  # (chave, rótulo, editor)
        for row, (label, action) in enumerate(commands):
            item = QTableWidgetItem(action.icon(), label)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item)
            editor = QKeySequenceEdit(action.shortcut())
            editor.setClearButtonEnabled(True)
            editor.setMaximumSequenceLength(1)
            self.table.setCellWidget(row, 1, editor)
            self._rows.append((action.objectName(), label, editor))

        restore = QPushButton(tr("Restaurar padrões"))
        restore.clicked.connect(self.restore_defaults)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(restore, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def editor(self, key: str) -> QKeySequenceEdit:
        return next(editor for row_key, _label, editor in self._rows if row_key == key)

    def restore_defaults(self):
        for key, _label, editor in self._rows:
            editor.setKeySequence((self._defaults.get(key) or [QKeySequence()])[0])

    def changes(self) -> dict[str, str | None]:
        """Atalho de cada comando em texto portável ("" = sem atalho), ou None se ficou o
        de fábrica."""
        result = {}
        for key, _label, editor in self._rows:
            sequence = editor.keySequence()
            defaults = self._defaults.get(key) or []
            unchanged = sequence == defaults[0] if defaults else sequence.isEmpty()
            result[key] = None if unchanged else _portable(sequence)
        return result

    def conflict(self) -> str | None:
        """Mensagem do primeiro atalho repetido (entre comandos ou com o visualizador)."""
        owners = {_portable(QKeySequence(keys)): None for keys in _RESERVED}
        changes = self.changes()
        for key, label, _editor in self._rows:
            chosen = changes[key]
            sequences = [_portable(s) for s in self._defaults.get(key, [])] if chosen is None else [chosen]
            for keys in filter(None, sequences):
                if keys in owners:
                    shown = QKeySequence(keys).toString(QKeySequence.SequenceFormat.NativeText)
                    other = owners[keys]
                    if other is None:
                        return tr("O atalho {keys} já é usado pelo visualizador.").format(keys=shown)
                    return tr('O atalho {keys} já é usado por "{command}".').format(keys=shown, command=other)
                owners[keys] = label
        return None

    def _accept(self):
        message = self.conflict()
        if message:
            QMessageBox.warning(self, tr("Atalhos de teclado"), message)
            return
        self.accept()
