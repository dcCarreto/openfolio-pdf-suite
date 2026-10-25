"""A aba Início: abrir um PDF (ou soltá-lo em qualquer parte dela), os atalhos de partida e os
arquivos recentes, com miniatura, pasta, páginas e data."""

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
    QGridLayout,
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
from ui import theme
from ui.app_events import pdf_paths_from_mime
from ui.i18n import tr
from ui.tools import ROW_OF
from ui.tools_center import ToolCard
from ui.viewer.render import render_page
from ui.viewer.viewer_icons import build_file_drop_icon, build_more_icon

# Os atalhos de partida, ao lado de "Abrir arquivo...": o que se faz sem ter um documento aberto.
_STARTERS = ["CreatePage", "MergePage", "ConvertPage", "CompressPage"]
MAX_WIDTH = 960
ROW_HEIGHT = 52
THUMB = QSize(28, 36)
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
            painter.fillRect(rect, QColor(t["raised"]))
        if index.row() > 0:
            painter.setPen(QPen(QColor(t["border"]), 1))
            painter.drawLine(rect.topLeft() + QPoint(12, 0), rect.topRight() - QPoint(12, 0))

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
        painter.setPen(QColor(t["text2"]))
        folder_rect = QRect(left, name_rect.bottom() + 2, text_right - left, 16)
        folder = painter.fontMetrics().elidedText(str(Path(path).parent), Qt.TextElideMode.ElideMiddle, folder_rect.width())
        painter.drawText(folder_rect, Qt.AlignmentFlag.AlignVCenter, folder)

        painter.setPen(QColor(t["text3"]))
        meta = QRect(more.left() - meta_width - 4, rect.top(), meta_width, rect.height())
        pages_text = tr("{count} página(s)").format(count=pages) if pages else ""
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
    tool_requested = Signal(int)  # a linha em ui.tools.SECTIONS
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
        outer_layout.setContentsMargins(40, 40, 40, 40)
        content = QWidget()
        content.setMaximumWidth(MAX_WIDTH)
        outer_layout.addStretch()
        outer_layout.addWidget(content, 100)
        outer_layout.addStretch()

        self._title = QLabel()
        self._title.setObjectName("HomeTitle")
        self._subtitle = QLabel()
        self._subtitle.setObjectName("pageSubtitle")

        # Zona de soltar, com "Abrir arquivo...".
        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("DropZone")
        self.drop_zone.setMinimumHeight(184)
        icon = QLabel()
        icon.setPixmap(build_file_drop_icon().pixmap(QSize(28, 28), QIcon.Mode.Selected))
        self._drop_title = QLabel()
        self._drop_title.setObjectName("EmptyTitle")
        self._drop_hint = QLabel()
        self._drop_hint.setProperty("ofRole", "secondary")
        self._open_button = QPushButton()
        self._open_button.setProperty("ofVariant", "primary")
        self._open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_button.clicked.connect(lambda: self.open_requested.emit(""))
        kbd = QLabel("Ctrl+O")
        kbd.setObjectName("Kbd")
        open_row = QHBoxLayout()
        open_row.addStretch()
        open_row.addWidget(self._open_button)
        open_row.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)
        open_row.addStretch()
        zone = QVBoxLayout(self.drop_zone)
        zone.setContentsMargins(24, 24, 24, 24)
        zone.setSpacing(8)
        zone.addStretch()
        zone.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        zone.addWidget(self._drop_title, 0, Qt.AlignmentFlag.AlignHCenter)
        zone.addWidget(self._drop_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        zone.addSpacing(6)
        zone.addLayout(open_row)
        zone.addStretch()

        shortcuts = QGridLayout()
        shortcuts.setSpacing(8)
        self.starter_cards: list[ToolCard] = []
        for position, class_name in enumerate(_STARTERS):
            card = ToolCard(ROW_OF[class_name], compact=True)
            card.clicked.connect(lambda _checked=False, r=card.row: self.tool_requested.emit(r))
            shortcuts.addWidget(card, position // 2, position % 2)
            self.starter_cards.append(card)
        top = QGridLayout()
        top.setHorizontalSpacing(16)
        top.addWidget(self.drop_zone, 0, 0)
        top.addLayout(shortcuts, 0, 1)
        top.setColumnStretch(0, 13)  # zona de soltar : atalhos = 1,3 : 2
        top.setColumnStretch(1, 20)

        self._recent_title = QLabel()
        self._recent_title.setObjectName("sectionTitle")
        self._clear_button = QPushButton()
        self._clear_button.setProperty("ofVariant", "ghost")
        self._clear_button.clicked.connect(self._clear_recent)
        recent_head = QHBoxLayout()
        recent_head.addWidget(self._recent_title)
        recent_head.addStretch()
        recent_head.addWidget(self._clear_button)
        self.recent_box = QFrame()
        self.recent_box.setObjectName("RecentBox")
        self.recent_list = RecentList()
        self.recent_list.open_requested.connect(self.open_requested)
        self.recent_list.menu_requested.connect(self._show_menu)
        box = QVBoxLayout(self.recent_box)
        box.setContentsMargins(1, 1, 1, 1)
        box.addWidget(self.recent_list)
        self._empty_label = QLabel()
        self._empty_label.setObjectName("pageSubtitle")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addSpacing(20)
        layout.addLayout(top)
        layout.addSpacing(28)
        layout.addLayout(recent_head)
        layout.addWidget(self.recent_box)
        layout.addWidget(self._empty_label)
        layout.addStretch(1)
        self.recent_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setWidget(outer)
        self.retranslate()

    def retranslate(self):
        self._title.setText(tr("Olá! Abra um PDF para começar."))
        self._subtitle.setText(tr("Tudo acontece neste computador. Nenhum arquivo sai daqui."))
        self._drop_title.setText(tr("Arraste um PDF para cá"))
        self._drop_hint.setText(tr("ou escolha um arquivo no computador"))
        self._open_button.setText(tr("Abrir arquivo..."))
        self._recent_title.setText(tr("Recentes"))
        self._clear_button.setText(tr("Limpar lista"))
        self._empty_label.setText(tr("Os PDFs abertos aparecem aqui."))
        for card in self.starter_cards:
            card.retranslate()
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
        self.recent_list.setFixedHeight(self.recent_list.sizeHint().height())
        self.recent_box.setVisible(has_recent)
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
        self.drop_zone.setProperty("dragOver", on)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

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
