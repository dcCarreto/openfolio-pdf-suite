"""Escolha entre poucas opções em cartões de rádio: nome, selo opcional ("recomendada") e, embaixo,
o efeito no arquivo ("Boa para enviar por e-mail. Fotos a 150 DPI.").

Os cartões apenas mostram o `combo` (QComboBox), que continua sendo a fonte da escolha. Com pouco
espaço (o rodapé do painel fora do estado Pronto, ou o painel com menos de 560 px de altura), os
cartões dão lugar ao próprio combo, numa linha de 36 px.
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout, QWidget

from ui.i18n import tr

SHORT_PANEL = 560  # abaixo disso, a linha compacta no lugar dos cartões


class _Card(QFrame):
    def __init__(self, radio: QRadioButton, badge: str, effect: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ChoiceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.radio = radio
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(radio)
        if badge:
            label = QLabel(tr(badge))
            label.setObjectName("ChoiceBadge")
            top.addWidget(label)
        top.addStretch()
        effect_label = QLabel(tr(effect))
        effect_label.setProperty("ofRole", "help")
        effect_label.setWordWrap(True)
        effect_label.setContentsMargins(26, 0, 0, 0)  # alinhado ao nome, depois do rádio
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(effect_label)
        radio.toggled.connect(self._restyle)

    def _restyle(self, checked: bool):
        self.setProperty("selected", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.radio.setChecked(True)
        self.radio.setFocus()
        super().mousePressEvent(event)


class ChoiceCards(QWidget):
    """`options`: (valor, nome, selo, efeito, rótulo curto do combo)."""

    def __init__(self, options: list[tuple[str, str, str, str, str]], parent=None):
        super().__init__(parent)
        self.combo = QComboBox()
        self.combo.setObjectName("ChoiceCombo")
        self.cards: list[_Card] = []
        cards = QWidget()
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(8)
        for index, (value, name, badge, effect, short) in enumerate(options):
            self.combo.addItem(tr(short), value)
            radio = QRadioButton(tr(name))
            radio.toggled.connect(lambda checked, i=index: self._choose(i) if checked else None)
            card = _Card(radio, badge, effect)
            cards_layout.addWidget(card)
            self.cards.append(card)
        self._cards = cards
        self.combo.currentIndexChanged.connect(self._sync)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(cards)
        layout.addWidget(self.combo)
        self._panel = None
        self.set_compact(False)

    def _choose(self, index: int):
        self.combo.setCurrentIndex(index)

    def _sync(self, index: int):
        if 0 <= index < len(self.cards):
            self.cards[index].radio.setChecked(True)

    def set_compact(self, compact: bool) -> None:
        self._cards.setVisible(not compact)
        self.combo.setVisible(compact)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync(self.combo.currentIndex())
        if self._panel is None:
            from ui.tool_panel import find_panel  # o painel importa as ferramentas, não o contrário

            self._panel = find_panel(self)
            if self._panel is not None:
                self._panel.installEventFilter(self)
                self._panel.footer.currentChanged.connect(self._follow_panel)
        self._follow_panel()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self._follow_panel()
        return False

    def _follow_panel(self, *_args):
        from ui.tool_panel import EMPTY, READY

        panel = self._panel
        if panel is not None:
            self.set_compact(panel.state() not in (READY, EMPTY) or panel.height() < SHORT_PANEL)
