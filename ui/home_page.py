"""A aba Início: abrir um PDF (ou soltá-lo em qualquer parte dela), os atalhos pelo que se quer
fazer e os arquivos recentes, com miniatura, pasta, páginas e data."""

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from core.base import open_pdfium
from core.progress import PDFIUM_LOCK
from ui import sidebar_icons, theme
from ui.app_events import pdf_paths_from_mime
from ui.i18n import plural, tr
from ui.icon_utils import in_accent
from ui.sidebar_icons import build_protect_icon
from ui.tools import TOOLS
from ui.viewer.render import render_page
from ui.viewer.viewer_icons import build_file_drop_icon, build_more_icon
from ui.widgets.flow_layout import FlowLayout

# "Ou comece pelo que você quer fazer": (rótulo, ferramenta, modo). "Transformar em Word" abre
# Converter › Do PDF para…, que começa no Word.
STARTERS = [
    ("Juntar PDFs", "MergePage", 0),
    ("Diminuir o tamanho", "CompressPage", 0),
    ("Assinar", "FillSignPage", 0),
    ("Transformar em Word", "ConvertPage", 0),
    ("Esconder dados pessoais", "RedactionPage", 0),
    ("Tornar pesquisável", "OCRPage", 0),
]
MAX_WIDTH = 880
ROW_HEIGHT = 52
THUMB = QSize(30, 40)
_PATH = Qt.ItemDataRole.UserRole

# Miniatura e número de páginas de cada recente, por (caminho, data de modificação): o arquivo
# só é aberto de novo se mudar.
_cache: dict[tuple[str, float], tuple[QPixmap | None, int | None]] = {}


def _key(path: str) -> tuple[str, float]:
    try:
        return path, os.path.getmtime(path)
    except OSError:
        return path, 0.0


def recent_info(path: str, ratio: float = 1.0) -> tuple[QPixmap | None, int | None]:
    """(miniatura da primeira página, número de páginas), do cache ou renderizada agora. Um
    PDF protegido ou ilegível fica sem miniatura e sem contagem."""
    key = _key(path)
    if key not in _cache:
        pixmap, pages = None, None
        try:
            with PDFIUM_LOCK:
                document = open_pdfium(path)
                try:
                    pages = len(document)
                    page = document[0]
                    width, height = page.get_size()
                    scale = min(THUMB.width() / width, THUMB.height() / height) if width and height else 0.05
                    pixmap = render_page(page, scale, ratio)
                    page.close()
                finally:
                    document.close()
        except Exception:
            pass
        _cache[key] = (pixmap, pages)
    return _cache[key]


def relative_date(timestamp: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    today = time.localtime(now)
    then = time.localtime(timestamp)
    days = (time.mktime(today[:3] + (0, 0, 0) + today[6:]) - time.mktime(then[:3] + (0, 0, 0) + then[6:])) // 86400
    if days <= 0:
        return tr("hoje, {hora}").format(hora=time.strftime("%H:%M", then))
    if days == 1:
        return tr("ontem")
    if days < 7:
        return tr("há {n} dias").format(n=int(days))
    return time.strftime("%d/%m/%Y", then)


def short_folder(path: str) -> str:
    """"Documentos › Clientes": as duas últimas pastas do caminho."""
    parts = Path(path).parent.parts[-2:]
    return " › ".join(part.rstrip("\\/") for part in parts if part.rstrip("\\/"))


def show_in_folder(path: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])  # noqa: S603, S607
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


class _RecentDelegate(QStyledItemDelegate):
    """Linha de 52 px: miniatura, nome, pasta (elidida no meio), páginas, data e o "…"."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index):
        path = index.data(_PATH)
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        hovered = option.state & QStyle.StateFlag.State_MouseOver
        selected = option.state & QStyle.StateFlag.State_Selected
        if hovered or selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["hover"]))
            painter.drawRoundedRect(rect.adjusted(0, 1, 0, -1), 8, 8)

        pixmap, pages = recent_info(path, painter.device().devicePixelRatioF())
        thumb = QRect(rect.left() + 14, rect.top() + (rect.height() - THUMB.height()) // 2, THUMB.width(), THUMB.height())
        painter.setPen(QPen(QColor(t["border_strong"]), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(thumb)
        if pixmap is not None:
            size = pixmap.deviceIndependentSize().toSize()
            painter.drawPixmap(thumb.center() - QPoint(size.width() // 2, size.height() // 2), pixmap)

        left = thumb.right() + 12
        more = self.more_rect(rect)
        meta_width = 150
        text_right = more.left() - meta_width - 8
        name_font = QFont(option.font)
        name_font.setPixelSize(13)
        name_font.setWeight(QFont.Weight.Medium)
        painter.setFont(name_font)
        painter.setPen(QColor(t["text"]))
        name_rect = QRect(left, rect.top() + 8, text_right - left, 18)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(Path(path).name, Qt.TextElideMode.ElideRight, name_rect.width()))
        small = QFont(option.font)
        small.setPixelSize(12)
        painter.setFont(small)
        painter.setPen(QColor(t["text3"]))
        folder_rect = QRect(left, name_rect.bottom() + 2, text_right - left, 16)
        folder = painter.fontMetrics().elidedText(short_folder(path), Qt.TextElideMode.ElideMiddle, folder_rect.width())
        painter.drawText(folder_rect, Qt.AlignmentFlag.AlignVCenter, folder)

        meta = QRect(more.left() - meta_width - 4, rect.top(), meta_width, rect.height())
        pages_text = plural(pages, "1 página", "{count} páginas") if pages else ""
        date = relative_date(_key(path)[1]) if _key(path)[1] else ""
        painter.drawText(meta, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, " · ".join(p for p in (pages_text, date) if p))
        build_more_icon().paint(painter, more.adjusted(6, 6, -6, -6))
        painter.restore()

    @staticmethod
    def more_rect(rect: QRect) -> QRect:
        return QRect(rect.right() - 40, rect.top() + (rect.height() - 28) // 2, 28, 28)


class RecentList(QListWidget):
    """A lista dos recentes: clique abre; o "…" (ou o botão direito) abre o menu da linha."""

    open_requested = Signal(str)
    menu_requested = Signal(str, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RecentList")
        self.setItemDelegate(_RecentDelegate(self))
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.itemActivated.connect(lambda item: self.open_requested.emit(item.data(_PATH)))

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        rect = self.visualItemRect(item)
        if _RecentDelegate.more_rect(rect).contains(event.position().toPoint()):
            self.menu_requested.emit(item.data(_PATH), self.viewport().mapToGlobal(_RecentDelegate.more_rect(rect).bottomLeft()))
        else:
            self.open_requested.emit(item.data(_PATH))
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            self.menu_requested.emit(item.data(_PATH), event.globalPos())

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), max(1, self.count()) * ROW_HEIGHT + 2)


class HomePage(QScrollArea):
    open_requested = Signal(str)  # o caminho; vazio para escolher o arquivo
    tool_requested = Signal(str, int)  # a ferramenta (ui.tools.TOOLS) e o modo
    recent_changed = Signal()  # a lista de recentes mudou aqui (limpar, remover)

    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)
        self._preferences = preferences

        outer = QWidget()
        outer.setObjectName("homeContent")
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(40, 40, 40, 40)  # 40 px no topo, coluna de 880
        content = QWidget()
        content.setMaximumWidth(MAX_WIDTH)
        outer_layout.addStretch()
        outer_layout.addWidget(content, 100)
        outer_layout.addStretch()

        self._title = QLabel()
        self._title.setObjectName("HomeTitle")
        self._privacy_icon = QLabel()
        self._subtitle = QLabel()
        self._subtitle.setObjectName("pageSubtitle")
        privacy = QHBoxLayout()
        privacy.setSpacing(6)
        privacy.addWidget(self._privacy_icon)
        privacy.addWidget(self._subtitle, 1)

        # Zona de soltar: grande e centralizada sem recentes; uma faixa de 96 px com eles. As
        # duas ficam prontas e só uma aparece (`drop_zone` é a que está à mostra).
        self._zones: dict[bool, QFrame] = {}
        self._zone_texts: list[tuple[QLabel, QLabel, QPushButton]] = []
        for compact in (False, True):
            zone = QFrame()
            zone.setObjectName("DropZone")
            zone.setFixedHeight(96 if compact else 240)
            icon = QLabel()
            size = 28 if compact else 36
            icon.setPixmap(build_file_drop_icon().pixmap(QSize(size, size), QIcon.Mode.Selected))
            title = QLabel()
            title.setObjectName("EmptyTitle")
            hint = QLabel()
            hint.setProperty("ofRole", "secondary")
            button = QPushButton()
            button.setProperty("ofVariant", "primary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda: self.open_requested.emit(""))
            kbd = QLabel("Ctrl O")
            kbd.setObjectName("Kbd")
            open_row = QHBoxLayout()
            open_row.setSpacing(8)
            open_row.addWidget(button)
            open_row.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            texts.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft if compact else Qt.AlignmentFlag.AlignHCenter)
            texts.addWidget(hint, 0, Qt.AlignmentFlag.AlignLeft if compact else Qt.AlignmentFlag.AlignHCenter)
            if compact:
                texts.insertStretch(0)  # na faixa, título e dica juntos no meio da altura
                texts.addStretch()
                layout_zone = QHBoxLayout(zone)
                layout_zone.setContentsMargins(24, 0, 24, 0)
                layout_zone.setSpacing(16)
                layout_zone.addWidget(icon)
                layout_zone.addLayout(texts, 1)
                layout_zone.addLayout(open_row)
            else:
                column = QVBoxLayout(zone)
                column.setContentsMargins(24, 24, 24, 24)
                column.setSpacing(8)
                column.addStretch()
                column.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
                column.addLayout(texts)
                column.addSpacing(8)
                open_row.insertStretch(0)
                open_row.addStretch()
                column.addLayout(open_row)
                column.addStretch()
            self._zones[compact] = zone
            self._zone_texts.append((title, hint, button))
        self.drop_zone = self._zones[False]

        # Ou comece pelo que você quer fazer.
        self._starters_title = QLabel()
        self._starters_title.setProperty("ofRole", "section")
        starters = QWidget()
        starters_layout = FlowLayout(starters, spacing=8)
        self.starter_buttons: list[QPushButton] = []
        for label, tool_id, mode in STARTERS:
            button = QPushButton(in_accent(getattr(sidebar_icons, TOOLS[tool_id].icon)()), "")
            button.setObjectName("StarterButton")
            button.setIconSize(QSize(18, 18))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("label", label)
            button.clicked.connect(lambda _checked=False, t=tool_id, m=mode: self.tool_requested.emit(t, m))
            starters_layout.addWidget(button)
            self.starter_buttons.append(button)

        self._recent_title = QLabel()
        self._recent_title.setObjectName("sectionTitle")
        self._clear_button = QPushButton()
        self._clear_button.setProperty("ofVariant", "ghost")
        self._clear_button.clicked.connect(self._clear_recent)
        recent_head = QHBoxLayout()
        recent_head.addWidget(self._recent_title)
        recent_head.addStretch()
        recent_head.addWidget(self._clear_button)
        self.recent_list = RecentList()
        self.recent_list.open_requested.connect(self.open_requested)
        self.recent_list.menu_requested.connect(self._show_menu)
        self.recent_box = self.recent_list  # nome antigo
        self._empty_label = QLabel()
        self._empty_label.setProperty("ofRole", "help")
        self._empty_label.setWordWrap(True)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addLayout(privacy)
        layout.addSpacing(22)
        layout.addWidget(self._zones[False])
        layout.addWidget(self._zones[True])
        layout.addSpacing(28)
        layout.addWidget(self._starters_title)
        layout.addSpacing(4)
        layout.addWidget(starters)
        layout.addSpacing(28)
        layout.addLayout(recent_head)
        layout.addWidget(self.recent_list)
        layout.addWidget(self._empty_label)
        layout.addStretch(1)
        self.recent_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setWidget(outer)
        self.retranslate()

    def retranslate(self):
        self._title.setText(tr("Olá! Abra um PDF para começar."))
        self._privacy_icon.setPixmap(build_protect_icon("success").pixmap(QSize(16, 16)))
        self._subtitle.setText(tr("Tudo acontece neste computador. Nenhum arquivo sai daqui."))
        for title, hint, button in self._zone_texts:
            title.setText(tr("Arraste um PDF para cá"))
            hint.setText(tr("ou escolha um arquivo no computador"))
            button.setText(tr("Abrir arquivo..."))
        self._starters_title.setText(tr("Ou comece pelo que você quer fazer"))
        for button in self.starter_buttons:
            button.setText(tr(button.property("label")))
        self._recent_title.setText(tr("Recentes"))
        self._clear_button.setText(tr("Limpar lista"))
        self._empty_label.setText(tr("Os PDFs que você abrir aparecem aqui, para voltar a eles com um clique."))
        self.refresh()

    def refresh(self):
        """Relê a lista de recentes (a aba Início é mostrada de novo a cada visita)."""
        self.recent_list.clear()
        for path in self._preferences.recent_files():
            item = QListWidgetItem(Path(path).name)
            item.setData(_PATH, path)
            item.setToolTip(path)
            self.recent_list.addItem(item)
        has_recent = self.recent_list.count() > 0
        self._zones[True].setVisible(has_recent)
        self._zones[False].setVisible(not has_recent)
        self.drop_zone = self._zones[has_recent]
        self.recent_list.setFixedHeight(self.recent_list.sizeHint().height())
        self.recent_list.setVisible(has_recent)
        self._clear_button.setVisible(has_recent)
        self._empty_label.setVisible(not has_recent)
        self.recent_list.viewport().update()

    def _clear_recent(self):
        self._preferences.clear_recent_files()
        self.refresh()
        self.recent_changed.emit()

    def _show_menu(self, path: str, position: QPoint):
        menu = QMenu(self)
        menu.addAction(tr("Abrir")).triggered.connect(lambda: self.open_requested.emit(path))
        menu.addAction(tr("Mostrar na pasta")).triggered.connect(lambda: show_in_folder(path))
        menu.addSeparator()
        menu.addAction(tr("Remover da lista")).triggered.connect(lambda: self.remove_recent(path))
        menu.popup(position)
        self._menu = menu  # o menu precisa viver até ser fechado

    def remove_recent(self, path: str) -> None:
        self._preferences.remove_recent_file(path)
        self.refresh()
        self.recent_changed.emit()

    # -- soltar um PDF em qualquer parte do Início --------------------------------------

    def _set_drag_over(self, on: bool):
        for zone in self._zones.values():
            zone.setProperty("dragOver", on)
            zone.style().unpolish(zone)
            zone.style().polish(zone)

    def dragEnterEvent(self, event):
        if pdf_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drag_over(False)

    def dropEvent(self, event):
        self._set_drag_over(False)
        paths = pdf_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            for path in paths:
                self.open_requested.emit(path)
