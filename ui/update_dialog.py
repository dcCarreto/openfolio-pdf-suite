"""Atualização disponível: o que mudou (do CHANGELOG.md) e o consentimento do usuário."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout

from core.updates import Update
from ui.i18n import tr


class UpdateDialog(QDialog):
    """Mostra o que a atualização traz. Aceitar baixa e instala (`can_install`) ou abre a
    página dela no navegador; "Agora não" não faz nada."""

    def __init__(self, update: Update, can_install: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Atualização disponível"))
        self.resize(560, 460)

        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(update.notes or tr("(A atualização não traz descrição.)"))

        if can_install:
            plan = tr(
                "Se você aceitar, o app baixa a atualização, confere o arquivo e fecha para "
                "instalá-la; ao terminar, ele abre de novo. Seus documentos não são tocados."
            )
            accept_text = tr("Baixar e instalar")
        else:
            plan = tr("Se você aceitar, a página da atualização abre no navegador para você baixá-la.")
            accept_text = tr("Abrir a página")
        plan_label = QLabel(plan)
        plan_label.setWordWrap(True)

        buttons = QDialogButtonBox()
        self.accept_button = buttons.addButton(accept_text, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("Agora não"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Há uma atualização do OpenFolio PDF Suite. O que mudou:")))
        layout.addWidget(self.notes, 1)
        layout.addWidget(plan_label)
        layout.addWidget(buttons)
