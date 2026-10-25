"""Atualização disponível: de quando é a edição nova, o que ela traz (do CHANGELOG.md) e o
consentimento do usuário. Nada é baixado antes de "Baixar e instalar"."""

import re

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from core.updates import Update, version_key
from core.version import APP_VERSION
from ui.i18n import EN_US, get_language, tr
from ui.preferences import preferences
from ui.viewer.viewer_icons import build_update_icon

MAX_ITEMS = 5
_MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
              "outubro", "novembro", "dezembro"]  # fmt: skip
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]  # fmt: skip


def edition_date(version: str) -> str:
    """"v2026.10.22" -> "22 de outubro de 2026" (ou "October 22, 2026"); vazio se não for uma
    data."""
    key = version_key(version or "")
    if key is None or not (1 <= key[1] <= 12 and 1 <= key[2] <= 31) or key[0] < 2000:
        return ""
    year, month, day = key[0], key[1], key[2]
    if get_language() == EN_US:
        return f"{_MONTHS_EN[month - 1]} {day}, {year}"
    return f"{day} de {_MONTHS_PT[month - 1]} de {year}"


def highlights(notes: str, limit: int = MAX_ITEMS) -> str:
    """Os primeiros itens da lista do que mudou, em Markdown; sem lista, o texto todo."""
    items: list[str] = []
    for line in notes.splitlines():
        bullet = re.match(r"\s*[-*]\s+(.*)", line)
        if bullet:
            items.append(bullet.group(1).strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()  # continuação do item anterior
    if not items:
        return notes.strip()
    return "\n".join(f"- {item}" for item in items[:limit])


class UpdateDialog(QDialog):
    """A moldura é a do sistema; só o conteúdo segue o tema. Esc é "Agora não"."""

    def __init__(self, update: Update, can_install: bool, parent=None, current: str = APP_VERSION):
        super().__init__(parent)
        self.setObjectName("OfDialog")
        self.setWindowTitle(tr("Atualização disponível"))
        self.setFixedWidth(480)
        self._update = update

        tile = QLabel()
        tile.setObjectName("IconTile")
        tile.setFixedSize(40, 40)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(build_update_icon().pixmap(QSize(22, 22), QIcon.Mode.Selected))
        title = QLabel(tr("Atualização disponível"))
        title.setObjectName("DialogTitle")
        new, mine = edition_date(update.version), edition_date(current)
        when = tr("Edição de {data}.").format(data=new) if new else ""
        if mine:
            when = f"{when} {tr('Você usa a de {data}.').format(data=mine)}".strip()
        self.when_label = QLabel(when)
        self.when_label.setProperty("ofRole", "secondary")
        self.when_label.setWordWrap(True)
        self.when_label.setVisible(bool(when))
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(title)
        heading.addWidget(self.when_label)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(heading, 1)

        news_title = QLabel(tr("Novidades").upper())
        news_title.setProperty("ofRole", "section")
        self.notes = QTextBrowser()
        self.notes.setObjectName("UpdateNotes")
        self.notes.setFrameShape(QFrame.Shape.NoFrame)
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(highlights(update.notes) or tr("(A atualização não traz descrição.)"))
        self.notes.document().setIndentWidth(14)  # o recuo padrão da lista é largo demais aqui
        self.notes.document().setDocumentMargin(0)
        self.notes.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        news = QFrame()
        news.setObjectName("UpdateNews")
        news_layout = QVBoxLayout(news)
        news_layout.setContentsMargins(14, 12, 14, 12)
        news_layout.setSpacing(6)
        news_layout.addWidget(news_title)
        news_layout.addWidget(self.notes)

        caption = QLabel(
            tr("Nada é baixado nem instalado sem a sua confirmação. Seus documentos abertos são preservados.")
        )
        caption.setProperty("ofRole", "secondary")
        caption.setWordWrap(True)
        self.notify_box = QCheckBox(tr("Avisar quando houver uma nova edição"))
        self.notify_box.setChecked(preferences().check_updates_on_start())
        self.notify_box.toggled.connect(preferences().set_check_updates_on_start)

        self.later_button = QPushButton(tr("Agora não"))
        self.later_button.setProperty("ofVariant", "ghost")
        self.later_button.setObjectName("BorderedGhost")
        self.later_button.clicked.connect(self.reject)
        self.notes_button = QPushButton(tr("Ver notas completas"))
        self.notes_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(update.page)))
        if can_install:
            self.accept_button = QPushButton(tr("Baixar e instalar"))
            self.accept_button.setToolTip(
                tr(
                    "Se você aceitar, o app baixa a atualização, confere o arquivo e fecha para "
                    "instalá-la; ao terminar, ele abre de novo. Seus documentos não são tocados."
                )
            )
        else:
            self.accept_button = QPushButton(tr("Abrir a página"))
            self.accept_button.setToolTip(
                tr("Se você aceitar, a página da atualização abre no navegador para você baixá-la.")
            )
        self.accept_button.setProperty("ofVariant", "primary")
        self.accept_button.setDefault(True)
        self.accept_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.notes_button)
        buttons.addWidget(self.accept_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addWidget(news)
        layout.addWidget(caption)
        layout.addWidget(self.notify_box)
        layout.addLayout(buttons)
        self.accept_button.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_notes()
        self.accept_button.setFocus()  # Enter baixa e instala; Esc é "Agora não"

    def _fit_notes(self):
        """As novidades inteiras, sem rolagem (até 220 px): medidas já com a fonte e a largura
        de verdade."""
        document = self.notes.document()
        document.setDefaultFont(self.notes.font())
        document.setTextWidth(self.notes.viewport().width())
        self.notes.setFixedHeight(min(240, int(document.size().height()) + 16))
