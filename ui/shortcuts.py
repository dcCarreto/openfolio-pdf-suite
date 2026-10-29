"""Paleta de comandos (Ctrl+K) e atalhos de teclado configuráveis (A18).

Os dois diálogos recebem a lista de comandos da janela principal: pares (rótulo, QAction),
em que o `objectName` da ação é a chave estável usada nas preferências.
"""

import unicodedata

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
from ui.tools import CATEGORIES
from ui.viewer.viewer_icons import build_search_icon

# Teclas que o visualizador e as abas já usam (ui/viewer/pdf_viewer.py, compare_view.py,
# organize_page.py): um comando nelas tiraria a tecla de lá.
_RESERVED = (
    "Ctrl+F", "Ctrl+G", "Ctrl+C", "Ctrl+=", "Ctrl++", "Ctrl+-", "Ctrl+0",
    "PgDown", "PgUp", "Right", "Left", "Home", "End", "F3", "Shift+F3", "Del",
)

_NAVIGATION_KEYS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown)


def fold_text(text: str) -> str:
    """Minúsculas sem acento, para "acoes" achar "Ações"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def _portable(sequence: QKeySequence) -> str:
    return sequence.toString(QKeySequence.SequenceFormat.PortableText)


# Grupos da paleta, na ordem em que aparecem: (chave, título).
GROUPS = [
    ("tools", "Ferramentas"),
    ("view", "Exibir"),
    ("navigate", "Navegar"),
    ("recent", "Arquivos recentes"),
    ("actions", "Ações"),
]
MAX_PER_GROUP = 8  # sem filtro de categoria; com ele (Tab), todos os do grupo
_NAVIGATION_COMMANDS = {"view.home", "view.tools"}
_CATEGORY_OF = {class_name: name for name, class_names in CATEGORIES for class_name in class_names}
ROW_HEIGHT = 40
HEADER_HEIGHT = 26
# Dados de cada linha (o texto do item, "Menu › Ação    atalho", é o que o leitor de tela lê).
_NAME, _CONTEXT, _KEYS, _GROUP, _HEADER = (Qt.ItemDataRole.UserRole + n for n in range(5))


def command_group(action) -> str:
    """O grupo de um comando, pela chave estável dele (`objectName`)."""
    key = action.objectName()
    if key.startswith("tool."):
        return "tools"
    if key in _NAVIGATION_COMMANDS or key.startswith("navigate."):
        return "navigate"
    if key.startswith("view."):
        return "view"
    if key.startswith("recent."):
        return "recent"
    return "actions"


class _PaletteDelegate(QStyledItemDelegate):
    """Linha de 40 px: ícone, nome, contexto e a tecla; a primeira de cada grupo leva o título
    do grupo em cima."""

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
            painter.drawText(rect.adjusted(14, 8, -14, 0).topLeft() + QPoint(0, 11), tr(title))
            rect.setTop(rect.top() + HEADER_HEIGHT)
        row = rect.adjusted(6, 2, -6, -2)
        current = bool(option.state & QStyle.StateFlag.State_Selected)
        if current:
            painter.setPen(QPen(QColor(t["accent_line"]), 1))
            painter.setBrush(QColor(t["accent_fill"]))
            painter.drawRoundedRect(QRectF(row), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["raised"]))
            painter.drawRoundedRect(QRectF(row), 8, 8)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        icon_rect = QRect(row.left() + 10, row.center().y() - 8, 17, 17)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, icon_rect, mode=QIcon.Mode.Selected if current else QIcon.Mode.Normal)
        left = icon_rect.right() + 12
        keys = index.data(_KEYS) or ""
        small = QFont(base)
        small.setPixelSize(11)
        keys_width = QFontMetrics(small).horizontalAdvance(keys) + 14 if keys else 0
        if keys:
            box = QRectF(row.right() - 10 - keys_width, row.center().y() - 10, keys_width, 20)
            painter.setFont(small)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent_line" if current else "border_strong"]), 1))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(QColor(t["accent_strong" if current else "text2"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, keys)
        name_font = QFont(base)
        name_font.setPixelSize(13)
        name_font.setWeight(QFont.Weight.Medium)
        painter.setFont(name_font)
        name = index.data(_NAME) or ""
        name_width = painter.fontMetrics().horizontalAdvance(name)
        available = row.right() - 20 - keys_width - left
        painter.setPen(QColor(t["text"]))
        shown = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, available)
        painter.drawText(QRect(left, row.top(), available, row.height()), Qt.AlignmentFlag.AlignVCenter, shown)
        context = index.data(_CONTEXT) or ""
        if context and name_width + 12 < available:
            context_font = QFont(base)
            context_font.setPixelSize(12)
            painter.setFont(context_font)
            painter.setPen(QColor(t["text3"]))
            context_rect = QRect(left + name_width + 10, row.top(), available - name_width - 10, row.height())
            elided = painter.fontMetrics().elidedText(context, Qt.TextElideMode.ElideRight, context_rect.width())
            painter.drawText(context_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        painter.restore()


class CommandPalette(QDialog):
    """Ctrl+K: um campo de busca sobre a janela escurecida e os comandos habilitados, em grupos
    (Ferramentas, Exibir, Navegar, Arquivos recentes, Ações). Filtra pelo que se digita (nome,
    menu ou descrição, sem acento); Tab filtra por grupo; Enter ou clique escolhe, e `chosen`
    fica com a ação.

    `extras` são comandos que não estão nos menus (documentos abertos, arquivos recentes), como
    pares (rótulo, QAction) — o grupo sai do `objectName` ("navigate.", "recent.")."""

    def __init__(self, commands, parent=None, extras=()):
        super().__init__(parent)
        self.setWindowTitle(tr("Paleta de comandos"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.chosen = None
        self._category: str | None = None

        self.frame = QFrame(self)
        self.frame.setObjectName("CommandPalette")
        self.frame.setFixedWidth(640)
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
        self.list.setMinimumHeight(8 * ROW_HEIGHT)
        footer = QWidget()
        footer.setObjectName("PaletteFooter")
        footer.setFixedHeight(36)
        hints = QLabel(tr("↑ ↓ navegar · Enter executar · Tab filtrar por categoria"))
        hints.setProperty("ofRole", "secondary")
        where = QLabel(tr("Atalhos em Editar › Atalhos de teclado"))
        where.setProperty("ofRole", "secondary")
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

        self._actions = []
        self._haystacks = []
        entries = [(label, action) for label, action in [*commands, *extras] if action.isEnabled()]
        order = {key: position for position, (key, _title) in enumerate(GROUPS)}
        entries.sort(key=lambda entry: order[command_group(entry[1])])  # estável: a ordem dos menus fica
        for label, action in entries:
            keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            item = QListWidgetItem(action.icon(), f"{label}    {keys}" if keys else label)
            context, _sep, _name = label.rpartition(" › ")
            if command_group(action) == "recent":
                context = action.statusTip()  # a pasta
            elif action.objectName().startswith("tool."):
                context = tr(_CATEGORY_OF.get(action.objectName()[5:], context))
            item.setData(_NAME, action.text())
            item.setData(_CONTEXT, context)
            item.setData(_KEYS, keys)
            item.setData(_GROUP, command_group(action))
            self.list.addItem(item)
            self._actions.append(action)
            self._haystacks.append(fold_text(f"{label} {action.statusTip()}"))

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run)
        self.list.itemClicked.connect(self._run)
        self.list.itemActivated.connect(self._run)
        self._filter("")

    # -- filtro -----------------------------------------------------------------------

    def _filter(self, *_args):
        words = fold_text(self.search.text()).split()
        first = -1
        shown: dict[str, int] = {}
        for row, haystack in enumerate(self._haystacks):
            item = self.list.item(row)
            group = item.data(_GROUP)
            visible = all(word in haystack for word in words) and self._category in (None, group)
            if visible and self._category is None and shown.get(group, 0) >= MAX_PER_GROUP:
                visible = False
            item.setHidden(not visible)
            item.setData(_HEADER, visible and group not in shown)
            if visible:
                shown[group] = shown.get(group, 0) + 1
                first = row if first < 0 else first
        self.list.doItemsLayout()  # as linhas com título mudaram de altura
        self.list.setCurrentRow(first)

    def set_category(self, category: str | None) -> None:
        self._category = category
        title = dict(GROUPS).get(category or "", "")
        self.category_label.setText(tr(title))
        self.category_label.setVisible(category is not None)
        self._filter()

    def _next_category(self, step: int):
        keys = [None] + [key for key, _title in GROUPS]
        self.set_category(keys[(keys.index(self._category) + step) % len(keys)])

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            # Setas e PgUp/PgDn andam pela lista, sem tirar o foco do campo; Tab troca o grupo.
            if event.key() in _NAVIGATION_KEYS:
                QApplication.sendEvent(self.list, event)
                return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self._next_category(-1 if event.key() == Qt.Key.Key_Backtab else 1)
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
        self.frame.move(x, 88)
        super().showEvent(event)
        self.search.setFocus()
        motion.animate(self, b"windowOpacity", 0.0, 1.0, motion.FAST)
        motion.animate(self.frame, b"pos", QPoint(x, 80), QPoint(x, 88), motion.MEDIUM)

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
