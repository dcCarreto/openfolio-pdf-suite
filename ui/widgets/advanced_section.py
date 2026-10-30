"""Opções avançadas: uma linha "› Opções avançadas · resumo" que abre o conteúdo, recuado 24 px.
Começa recolhida e lembra, por ferramenta, como o usuário a deixou."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.i18n import tr
from ui.preferences import preferences
from ui.viewer.viewer_icons import build_caret_down_icon, build_caret_right_icon


class AdvancedSection(QWidget):
    def __init__(self, key: str, summary: str, content: QWidget, parent=None):
        super().__init__(parent)
        self._key = key
        self._summary = summary
        self.content = content
        self.toggle = QPushButton()
        self.toggle.setObjectName("AdvancedToggle")
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chevron = QLabel()
        self._title = QLabel()
        self._title.setObjectName("AdvancedTitle")
        self._summary_label = QLabel()
        self._summary_label.setProperty("ofRole", "help")
        for label in (self._chevron, self._title, self._summary_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self.toggle)
        row.setContentsMargins(4, 0, 8, 0)
        row.setSpacing(6)
        row.addWidget(self._chevron)
        row.addWidget(self._title)
        row.addWidget(self._summary_label, 1)
        self._indented = QWidget()
        indented = QVBoxLayout(self._indented)
        indented.setContentsMargins(24, 4, 0, 0)
        indented.addWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(self._indented)
        self.toggle.toggled.connect(self._set_open)
        self.toggle.setChecked(preferences().advanced_open(key))
        self._set_open(self.toggle.isChecked(), remember=False)
        self.retranslate()

    def retranslate(self) -> None:
        self._title.setText(tr("Opções avançadas"))
        self._summary_label.setText(f"· {tr(self._summary)}")
        self.toggle.setAccessibleName(f"{tr('Opções avançadas')}: {tr(self._summary)}")

    def is_open(self) -> bool:
        return self.toggle.isChecked()

    def _set_open(self, opened: bool, remember: bool = True) -> None:
        icon = build_caret_down_icon() if opened else build_caret_right_icon()
        self._chevron.setPixmap(icon.pixmap(QSize(14, 14)))
        self._indented.setVisible(opened)
        if remember:
            preferences().set_advanced_open(self._key, opened)
