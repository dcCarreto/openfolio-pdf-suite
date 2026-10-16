"""Combo de cores: algumas cores prontas e "Outra cor...", que abre o seletor do sistema."""

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QComboBox

from ui.i18n import tr

_PRESETS = [
    ("000000", "Preto"),
    ("ffffff", "Branco"),
    ("595959", "Cinza"),
    ("c62828", "Vermelho"),
    ("1565c0", "Azul"),
    ("2e7d32", "Verde"),
]
_CUSTOM = "custom"


def _swatch(hex_color: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(f"#{hex_color}"))
    return QIcon(pixmap)


class ColorCombo(QComboBox):
    """`color()` devolve a cor escolhida em hexadecimal, sem "#" (ex.: "ff0000")."""

    def __init__(self, default: str = "000000", parent=None):
        super().__init__(parent)
        for hex_color, name in _PRESETS:
            self.addItem(_swatch(hex_color), tr(name), hex_color)
        self.addItem(tr("Outra cor..."), _CUSTOM)
        self.setColor(default)
        self._last_index = self.currentIndex()
        self.activated.connect(self._on_activated)

    def color(self) -> str:
        return self.currentData()

    def setColor(self, hex_color: str) -> None:
        hex_color = hex_color.lower().lstrip("#")
        index = self.findData(hex_color)
        if index < 0:
            index = self.count() - 1
            self.insertItem(index, _swatch(hex_color), f"#{hex_color}", hex_color)
        self.setCurrentIndex(index)

    def _on_activated(self, index: int) -> None:
        if self.itemData(index) != _CUSTOM:
            self._last_index = index
            return
        chosen = QColorDialog.getColor(QColor(f"#{self.itemData(self._last_index)}"), self, tr("Escolher cor"))
        if chosen.isValid():
            self.setColor(chosen.name()[1:])
            self._last_index = self.currentIndex()
        else:
            self.setCurrentIndex(self._last_index)
