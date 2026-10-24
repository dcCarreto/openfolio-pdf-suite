"""A barra superior da janela (44 px), que junta a barra de menus e a linha de abas:

    [logo][Arquivo Editar Exibir Ajuda] | [Início][Ferramentas][doc.pdf ●] ... [+] [Buscar...  Ctrl K] [PT|EN]

As abas ficam na barra e as páginas no centro da janela: `DocumentTabs` é a pilha das páginas,
com a API de QTabWidget que a janela já usava, ligada à `DocTabBar` da barra.
"""

from typing import cast

from PySide6.QtCore import QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QWidget,
)

from ui import i18n, theme
from ui.i18n import tr
from ui.preferences import preferences
from ui.viewer.viewer_icons import build_search_icon

FIXED_TABS = ("home", "tools")  # Início e Ferramentas: sempre as duas primeiras, não fecham


class DocTabBar(QTabBar):
    """As abas da janela. As de documento se reordenam arrastando; Início e Ferramentas ficam
    sempre na frente (voltam ao lugar se outra aba for solta antes delas)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DocTabs")
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.setUsesScrollButtons(True)
        self.setMovable(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setIconSize(QSize(16, 16))

    def mousePressEvent(self, event):
        self.setMovable(self.tabAt(event.position().toPoint()) >= len(FIXED_TABS))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        for target, tag in enumerate(FIXED_TABS):
            index = next((i for i in range(self.count()) if self.tabData(i) == tag), target)
            if index != target:
                self.moveTab(index, target)


class DocumentTabs(QStackedWidget):
    """As páginas das abas (Início, Ferramentas e uma por documento), com a API de QTabWidget."""

    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar = DocTabBar()
        self._bar.currentChanged.connect(self._on_bar_changed)
        self._bar.tabMoved.connect(self._on_tab_moved)
        self._bar.tabCloseRequested.connect(self.tabCloseRequested)

    def tabBar(self) -> DocTabBar:
        return self._bar

    def addTab(self, widget: QWidget, *args) -> int:
        """`addTab(widget, texto)` ou `addTab(widget, ícone, texto)`, como no QTabWidget."""
        icon, text = (QIcon(), args[0]) if len(args) == 1 else args
        index = self.addWidget(widget)
        self._bar.insertTab(index, icon, text)
        return index

    def removeTab(self, index: int) -> None:
        widget = cast(QWidget, self.widget(index))
        self._bar.blockSignals(True)
        self._bar.removeTab(index)
        self._bar.blockSignals(False)
        self.removeWidget(widget)
        super().setCurrentIndex(self._bar.currentIndex())

    def setCurrentIndex(self, index: int) -> None:
        self._bar.setCurrentIndex(index)
        super().setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget) -> None:
        self.setCurrentIndex(self.indexOf(widget))

    def tabText(self, index: int) -> str:
        return self._bar.tabText(index)

    def setTabText(self, index: int, text: str) -> None:
        self._bar.setTabText(index, text)

    def setTabToolTip(self, index: int, text: str) -> None:
        self._bar.setTabToolTip(index, text)

    def setTabIcon(self, index: int, icon: QIcon) -> None:
        self._bar.setTabIcon(index, icon)

    def _on_bar_changed(self, index: int) -> None:
        if index >= 0:
            super().setCurrentIndex(index)

    def _on_tab_moved(self, source: int, target: int) -> None:
        widget = cast(QWidget, self.widget(source))
        self.blockSignals(True)  # a página da frente não muda: nada a avisar
        self.removeWidget(widget)
        self.insertWidget(target, widget)
        super().setCurrentIndex(self._bar.currentIndex())
        self.blockSignals(False)


class TabCloseButton(QAbstractButton):
    """O "x" da aba de documento. Com alterações não salvas, vira um ponto cheio (o "x" volta
    com o mouse em cima): o aviso não depende só de cor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._dirty = False

    def is_dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(20, 20)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        t = theme.tokens()
        hover = self.underMouse()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["pressed"]))
            painter.drawRoundedRect(QRectF(self.rect()), 5, 5)
        if self._dirty and not hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["text2"]))
            painter.drawEllipse(QRectF(6, 6, 8, 8))
            return
        pen = QPen(QColor(t["text"] if hover else t["text2"]), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(6.5, 6.5, 13.5, 13.5)
        painter.drawLine(13.5, 6.5, 6.5, 13.5)


class BusySpinner(QWidget):
    """Arco de 270° girando: uma operação em andamento. Parado com as animações desligadas."""

    def __init__(self, size: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0)
        self._animation.setEndValue(360)
        self._animation.setDuration(800)
        self._animation.setLoopCount(-1)
        self._animation.valueChanged.connect(self._turn)

    def _turn(self, angle):
        self._angle = int(angle)
        self.update()

    def is_spinning(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    def showEvent(self, event):
        if preferences().animations():
            self._animation.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._animation.stop()
        super().hideEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.tokens()["accent"]), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(self.rect()).adjusted(2, 2, -2, -2), (90 - self._angle) * 16, -270 * 16)


class LangSwitch(QWidget):
    """O idioma da interface em texto ("PT | EN"): leitores de tela leem o texto, não a bandeira."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        group = QButtonGroup(self)
        self.buttons: dict[str, QToolButton] = {}
        for language, text, name in ((i18n.PT_BR, "PT", "Português (Brasil)"), (i18n.EN_US, "EN", "English")):
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, lang=language: i18n.set_language(lang))
            group.addButton(button)
            layout.addWidget(button)
            self.buttons[language] = button
        self.retranslate()

    def retranslate(self):
        self.setAccessibleName(tr("Idioma da interface"))
        self.buttons[i18n.get_language()].setChecked(True)


class CommandLauncher(QPushButton):
    """Parece um campo de busca e abre a paleta de comandos. Estreito, vira só a lupa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CommandLauncher")
        self.setIcon(build_search_icon())
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kbd = QLabel("Ctrl K")
        self._kbd.setObjectName("Kbd")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addStretch()
        layout.addWidget(self._kbd)
        self._compact = False
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self._kbd.setVisible(not compact)
        self.setFixedSize(32 if compact else 300, 32 if compact else 30)
        self.retranslate()

    def retranslate(self):
        label = tr("Buscar ferramentas e comandos")
        self.setText("" if self._compact else label)
        self.setToolTip(f"{label} (Ctrl+K)")
        self.setAccessibleName(label)


def bar_separator() -> QFrame:
    """O traço vertical de 1 x 20 px entre grupos de uma barra."""
    line = QFrame()
    line.setObjectName("BarSeparator")
    line.setFixedSize(1, 20)
    return line
