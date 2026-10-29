"""Paleta de comandos (Ctrl+K) e atalhos de teclado configuráveis (A18).

Os dois diálogos recebem a lista de comandos da janela principal: pares (rótulo, QAction),
em que o `objectName` da ação é a chave estável usada nas preferências.
"""

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import motion, theme
from ui.i18n import tr
from ui import search_index
from ui.search_index import fold_text  # noqa: F401 (usado por outros módulos daqui)
from ui.tools import TOOLS, mode_key
from ui.viewer.viewer_icons import build_search_icon

# Teclas que o visualizador e as abas já usam (ui/viewer/pdf_viewer.py, compare_view.py,
# organize_page.py): um comando nelas tiraria a tecla de lá.
_RESERVED = (
    "Ctrl+F", "Ctrl+G", "Ctrl+C", "Ctrl+=", "Ctrl++", "Ctrl+-", "Ctrl+0",
    "PgDown", "PgUp", "Right", "Left", "Home", "End", "F3", "Shift+F3", "Del",
)

_NAVIGATION_KEYS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown)
TOP = 72  # a caixa da paleta, a esta distância do topo da janela


def _portable(sequence: QKeySequence) -> str:
    return sequence.toString(QKeySequence.SequenceFormat.PortableText)


# Grupos da paleta, na ordem em que aparecem: (chave, título).
GROUPS = [
    ("tools", "Ferramentas"),
    ("commands", "Comandos"),
]
MAX_PER_GROUP = 8  # sem nada digitado; com uma busca, todos os que batem
ROW_HEIGHT = 52
HEADER_HEIGHT = 26
# Dados de cada linha (o texto do item, "nome    atalho", é o que o leitor de tela lê).
_NAME, _CONTEXT, _KEYS, _GROUP, _HEADER, _REASON, _TOOL = (Qt.ItemDataRole.UserRole + n for n in range(7))


def command_group(action) -> str:
    """O grupo de um comando, pela chave estável dele (`objectName`): as ferramentas e os modos
    delas, ou os outros comandos (menus, documentos abertos, arquivos recentes)."""
    key = action.objectName()
    return "tools" if key.startswith(("tool.", "mode.")) else "commands"


class _PaletteDelegate(QStyledItemDelegate):
    """Linha de 52 px: placa de ícone de 30, nome, uma linha de descrição, o motivo da busca
    ("por “cpf”") e o atalho; a primeira de cada grupo leva o título do grupo em cima."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_HEIGHT + (HEADER_HEIGHT if index.data(_HEADER) else 0))

    def paint(self, painter: QPainter, option, index):
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRect(option.rect)
        base = QFont(option.font)
        if index.data(_HEADER):
            header = QFont(base)
            header.setPixelSize(11)
            header.setWeight(QFont.Weight.DemiBold)
            painter.setFont(header)
            painter.setPen(QColor(t["text3"]))
            title = dict(GROUPS)[index.data(_GROUP)]
            painter.drawText(rect.adjusted(16, 8, -16, 0).topLeft() + QPoint(0, 11), tr(title))
            rect.setTop(rect.top() + HEADER_HEIGHT)
        row = rect.adjusted(6, 1, -6, -1)
        current = bool(option.state & QStyle.StateFlag.State_Selected)
        if current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["accent_fill"]))
            painter.drawRoundedRect(QRectF(row), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["hover"]))
            painter.drawRoundedRect(QRectF(row), 8, 8)
        tile = QRectF(row.left() + 10, row.center().y() - 15, 30, 30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["panel" if current else "raised"]))
        painter.drawRoundedRect(tile, 8, 8)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, tile.adjusted(6, 6, -6, -6).toRect(), mode=QIcon.Mode.Selected if current else QIcon.Mode.Normal)
        left = int(tile.right()) + 12
        small = QFont(base)
        small.setPixelSize(11)
        right = row.right() - 10
        if current:  # o "↵" diz que Enter abre
            painter.setFont(base)
            painter.setPen(QColor(t["accent_strong"]))
            painter.drawText(QRect(right - 16, row.top(), 16, row.height()), Qt.AlignmentFlag.AlignCenter, "↵")
            right -= 24
        keys = index.data(_KEYS) or ""
        if keys:
            width = QFontMetrics(small).horizontalAdvance(keys) + 12
            box = QRectF(right - width, row.center().y() - 10, width, 20)
            painter.setFont(small)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent_line" if current else "border_strong"]), 1))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(QColor(t["accent_strong" if current else "text2"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, keys)
            right = int(box.left()) - 8
        reason = index.data(_REASON) or ""
        if reason:
            reason_font = QFont(base)
            reason_font.setPixelSize(12)
            painter.setFont(reason_font)
            painter.setPen(QColor(t["text3"]))
            text = tr("por “{word}”").format(word=reason)
            width = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText(QRect(right - width, row.top(), width, row.height()), Qt.AlignmentFlag.AlignVCenter, text)
            right -= width + 10
        available = max(10, right - left)
        name_font = QFont(base)
        name_font.setPixelSize(13)
        name_font.setWeight(QFont.Weight.DemiBold if current else QFont.Weight.Medium)
        painter.setFont(name_font)
        painter.setPen(QColor(t["accent_strong" if current else "text"]))
        name = painter.fontMetrics().elidedText(index.data(_NAME) or "", Qt.TextElideMode.ElideRight, available)
        description = index.data(_CONTEXT) or ""
        name_rect = QRect(left, row.top() + (8 if description else 0), available, 18 if description else row.height())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, name)
        if description:
            description_font = QFont(base)
            description_font.setPixelSize(12)
            painter.setFont(description_font)
            painter.setPen(QColor(t["text2"]))
            shown = painter.fontMetrics().elidedText(description, Qt.TextElideMode.ElideRight, available)
            painter.drawText(QRect(left, row.top() + 26, available, 18), Qt.AlignmentFlag.AlignVCenter, shown)
        painter.restore()


class CommandPalette(QDialog):
    """Ctrl+K: um campo de busca sobre a janela escurecida, com as ferramentas (e os modos
    delas) e os comandos habilitados. Busca pelo índice das ferramentas (nome, descrição,
    sinônimos e nomes antigos; ver ui/search_index.py) e, nos comandos, pelo nome, o menu e a
    descrição. Tab entra nos modos da ferramenta destacada; Enter ou clique escolhe, e `chosen`
    fica com a ação.

    `extras` são comandos que não estão nos menus (documentos abertos, arquivos recentes), como
    pares (rótulo, QAction)."""

    def __init__(self, commands, parent=None, extras=()):
        super().__init__(parent)
        self.setWindowTitle(tr("Paleta de comandos"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.chosen = None
        self._modes_of = ""  # Tab: os modos desta ferramenta

        self.frame = QFrame(self)
        self.frame.setObjectName("CommandPalette")
        self.frame.setFixedWidth(620)
        self.search = QLineEdit()
        self.search.setObjectName("PaletteSearch")
        self.search.setPlaceholderText(tr("Buscar ferramentas e comandos"))
        self.search.addAction(build_search_icon(), QLineEdit.ActionPosition.LeadingPosition).setText(tr("Buscar"))
        self.search.installEventFilter(self)
        self.category_label = QLabel()
        self.category_label.setObjectName("PaletteCategory")
        self.category_label.hide()
        esc = QLabel("Esc")
        esc.setObjectName("Kbd")
        field = QWidget()
        field.setObjectName("PaletteField")
        field.setFixedHeight(52)
        field_layout = QHBoxLayout(field)
        field_layout.setContentsMargins(10, 0, 14, 0)
        field_layout.addWidget(self.search, 1)
        field_layout.addWidget(self.category_label)
        field_layout.addWidget(esc, 0, Qt.AlignmentFlag.AlignVCenter)
        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setItemDelegate(_PaletteDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setMinimumHeight(7 * ROW_HEIGHT)
        footer = QWidget()
        footer.setObjectName("PaletteFooter")
        footer.setFixedHeight(36)
        hints = QLabel(tr("↑↓ navegar · Enter abrir · Tab ver modos"))
        hints.setProperty("ofRole", "help")
        where = QLabel(tr("Busca também por sinônimos: cpf, word, rubrica…"))
        where.setProperty("ofRole", "help")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 0, 14, 0)
        footer_layout.addWidget(hints)
        footer_layout.addStretch()
        footer_layout.addWidget(where)
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(field)
        layout.addWidget(self.list, 1)
        layout.addWidget(footer)
        self.frame.setGraphicsEffect(theme.floating_shadow(self.frame, modal=True))

        index = {}
        for entry in search_index.entries():
            key = f"tool.{entry.tool.id}" if entry.mode is None else mode_key(entry.tool, entry.mode)
            index[key] = entry
        self._actions = []
        self._entries: list[search_index.Entry | None] = []
        self._haystacks = []
        entries = [(label, action) for label, action in [*commands, *extras] if action.isEnabled()]
        order = {key: position for position, (key, _title) in enumerate(GROUPS)}
        entries.sort(key=lambda entry: order[command_group(entry[1])])  # estável: a ordem dos menus fica
        for label, action in entries:
            keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            entry = index.get(action.objectName())
            if entry is not None:
                name = entry.title
                description = tr(entry.tool.description) if entry.mode is None else ""
            else:
                name, description = label, action.statusTip()
            item = QListWidgetItem(action.icon(), f"{name}    {keys}" if keys else name)
            item.setData(_NAME, name)
            item.setData(_CONTEXT, description)
            item.setData(_KEYS, keys)
            item.setData(_GROUP, command_group(action))
            item.setData(_TOOL, entry.tool.id if entry is not None else "")
            self.list.addItem(item)
            self._actions.append(action)
            self._entries.append(entry)
            self._haystacks.append(fold_text(f"{label} {action.statusTip()}"))

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run)
        self.list.itemClicked.connect(self._run)
        self.list.itemActivated.connect(self._run)
        self._filter("")

    # -- filtro -----------------------------------------------------------------------

    def _filter(self, *_args):
        query = self.search.text()
        words = fold_text(query).split()
        first = -1
        shown: dict[str, int] = {}
        for row, haystack in enumerate(self._haystacks):
            item = self.list.item(row)
            group = item.data(_GROUP)
            entry = self._entries[row]
            reason = ""
            if self._modes_of:
                visible = entry is not None and entry.tool.id == self._modes_of and entry.mode is not None
                visible = visible and search_index.match(entry, query)[0]
            elif entry is not None:
                # Sem nada digitado, só as ferramentas; os modos aparecem na busca ou com Tab.
                visible, reason = search_index.match(entry, query) if words else (entry.mode is None, "")
            else:
                visible = all(word in haystack for word in words)
            if visible and not words and not self._modes_of and shown.get(group, 0) >= MAX_PER_GROUP:
                visible = False
            item.setHidden(not visible)
            item.setData(_REASON, reason)
            item.setData(_HEADER, visible and group not in shown)
            if visible:
                shown[group] = shown.get(group, 0) + 1
                first = row if first < 0 else first
        self.list.doItemsLayout()  # as linhas com título mudaram de altura
        self.list.setCurrentRow(first)

    def show_modes(self, tool_id: str) -> None:
        """Só os modos da ferramenta `tool_id` ("" volta à lista toda)."""
        self._modes_of = tool_id
        self.category_label.setText(tr(TOOLS[tool_id].title) if tool_id else "")
        self.category_label.setVisible(bool(tool_id))
        self._filter()

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            # Setas e PgUp/PgDn andam pela lista, sem tirar o foco do campo; Tab entra nos
            # modos da ferramenta destacada e Shift+Tab sai deles.
            if event.key() in _NAVIGATION_KEYS:
                QApplication.sendEvent(self.list, event)
                return True
            if event.key() == Qt.Key.Key_Backtab or (event.key() == Qt.Key.Key_Tab and self._modes_of):
                self.show_modes("")
                return True
            if event.key() == Qt.Key.Key_Tab:
                row = self.list.currentRow()
                tool = self.list.item(row).data(_TOOL) if row >= 0 else ""
                if tool and len(TOOLS[tool].modes) > 1:
                    self.show_modes(tool)
                return True
        return super().eventFilter(watched, event)

    def _run(self, *_args):
        row = self.list.currentRow()
        if row >= 0 and not self.list.item(row).isHidden():
            self.chosen = self._actions[row]
            self.accept()

    # -- sobre a janela -----------------------------------------------------------------

    def showEvent(self, event):
        owner = self.parentWidget().window() if self.parentWidget() is not None else None
        if owner is not None:
            self.setGeometry(owner.geometry())  # cobre a janela: o fundo escurecido
        x = (self.width() - self.frame.width()) // 2
        self.frame.adjustSize()
        self.frame.move(x, TOP)
        super().showEvent(event)
        self.search.setFocus()
        motion.animate(self, b"windowOpacity", 0.0, 1.0, motion.FAST)
        motion.animate(self.frame, b"pos", QPoint(x, TOP - 4), QPoint(x, TOP), motion.MEDIUM)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color("scrim"))

    def mousePressEvent(self, event):
        if not self.frame.geometry().contains(event.position().toPoint()):
            self.reject()  # clicar fora fecha
        else:
            super().mousePressEvent(event)


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
