"""Contêiner padrão de página: título, subtítulo e conteúdo, com espaçamento consistente."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageContainer(QWidget):
    """Envolve o conteúdo de uma seção com um cabeçalho consistente (título + subtítulo)."""

    def __init__(self, title: str, subtitle: str, content: QWidget, parent=None):
        super().__init__(parent)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(4)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(12)
        layout.addWidget(content)
