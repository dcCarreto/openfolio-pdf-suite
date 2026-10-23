"""Campo de número de página com o botão "Página atual", que copia a página que o
visualizador está mostrando — para não ter de procurar e digitar o número."""

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSpinBox

from ui.i18n import tr


def with_current_page_button(spin: QSpinBox, session) -> QHBoxLayout:
    button = QPushButton(tr("Página atual"))
    button.setToolTip(tr("Usar a página que está no visualizador"))
    button.clicked.connect(lambda: spin.setValue(session.current_page() + 1))
    row = QHBoxLayout()
    row.addWidget(spin, 1)
    row.addWidget(button)
    return row
