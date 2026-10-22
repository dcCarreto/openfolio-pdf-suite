"""Ajuda > Sobre (M48): versão, arquivo de log e componentes de terceiros com as licenças."""

import json
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.version import DISTRIBUTION
from ui.i18n import tr

CHANGELOG_URL = "https://github.com/dcCarreto/openfolio-pdf-suite/blob/main/CHANGELOG.md"

# O que vai no app e não é um pacote Python (os pacotes vêm dos metadados instalados) nem
# biblioteca de um gerenciador de pacotes (vêm de THIRD_PARTY_DIR).
OTHER_COMPONENTS = [
    ("Qt", qVersion(), "LGPL-3.0-only"),
    ("PDFium", "—", "BSD-3-Clause"),
    ("Tesseract tessdata (eng, por, osd)", "4.1.0", "Apache-2.0"),
    ("DejaVu Fonts", "2.37", "Bitstream Vera"),
    ("sRGB v2 micro (Compact-ICC-Profiles)", "—", "CC0-1.0"),
]

# O Tesseract e as bibliotecas dele (e, no Linux, as do sistema que o Qt usa), com os textos
# das licenças: só no app empacotado (packaging/pyinstaller/third_party.py).
_BUNDLE = getattr(sys, "_MEIPASS", None)
THIRD_PARTY_DIR = Path(_BUNDLE) / "third-party" if _BUNDLE else None


def bundled_components() -> list[tuple[str, str, str]]:
    """(nome, versão, licença) de cada biblioteca de fora do Python que vai no app."""
    if THIRD_PARTY_DIR is None:
        return []
    try:
        rows = json.loads((THIRD_PARTY_DIR / "components.json").read_text(encoding="utf-8"))
        return [(name, version, license) for name, version, license in rows]
    except (OSError, ValueError):
        return []  # um build local sem os pacotes de origem (o spec avisa)


def _license(dist: metadata.Distribution) -> str:
    """A licença declarada pelo pacote: a expressão SPDX, o campo License (só a primeira
    linha, curta: alguns pacotes põem o texto inteiro ali) ou o classificador."""
    meta: Any = dist.metadata  # um email.message.Message; o stub não declara get()
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    text = (meta.get("License") or "").strip().splitlines()
    if text and len(text[0]) <= 60:
        return text[0]
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(classifiers) or "?"


def python_components() -> list[tuple[str, str, str]]:
    """(nome, versão, licença) de cada pacote de que o app depende, direta ou indiretamente."""
    found: dict[str, metadata.Distribution] = {}
    pending = [DISTRIBUTION]
    while pending:
        name = pending.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in found:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # dependência só de outra plataforma
        found[key] = dist
        for requirement in dist.requires or []:
            if "extra ==" not in requirement:
                pending.append(re.match(r"[A-Za-z0-9._-]+", requirement).group())  # type: ignore[union-attr]
    found.pop(DISTRIBUTION, None)
    return sorted(((dist.metadata["Name"], dist.version, _license(dist)) for dist in found.values()), key=lambda c: c[0].lower())


class AboutDialog(QDialog):
    def __init__(self, log_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Sobre o OpenFolio PDF Suite"))
        self.resize(640, 560)

        # Sem número de versão: há uma só, que recebe atualizações (core/updates.py).
        self.header = QLabel(
            "<b>OpenFolio PDF Suite</b><br><br>"
            + tr("Suite completa e open source de manipulação de PDF, 100% local, sem paywall.")
            + f'<br><br><a href="{CHANGELOG_URL}">'
            + tr("O que mudou em cada atualização")
            + "</a>"
        )
        self.header.setWordWrap(True)
        self.header.setOpenExternalLinks(True)

        self.log_edit = QLineEdit(str(log_path) if log_path else tr("(sem arquivo de log)"))
        self.log_edit.setReadOnly(True)
        open_folder = QPushButton(tr("Abrir pasta"))
        open_folder.setEnabled(log_path is not None)
        if log_path is not None:
            open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.parent))))
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_edit, 1)
        log_row.addWidget(open_folder)

        self.components_table = QTableWidget(0, 3)
        self.components_table.setHorizontalHeaderLabels([tr("Componente"), tr("Versão"), tr("Licença")])
        self.components_table.verticalHeader().setVisible(False)
        self.components_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, values in enumerate(OTHER_COMPONENTS + bundled_components() + python_components()):
            self.components_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)  # nomes e expressões de licença longos ficam cortados
                self.components_table.setItem(row, column, item)
        header = self.components_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(QLabel(tr("Arquivo de log (anexe-o ao relatar um problema):")))
        layout.addLayout(log_row)
        layout.addWidget(QLabel(tr("Componentes de terceiros:")))
        layout.addWidget(self.components_table, 1)
        note = QLabel(
            tr("Os textos das licenças dos pacotes Python vão junto com o app, nos metadados de cada um.")
            + " "
            + tr("O código-fonte das bibliotecas GPL e LGPL está em cada atualização, na página de releases.")
        )
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        licenses = QPushButton(tr("Licenças das bibliotecas"))
        licenses.setEnabled(THIRD_PARTY_DIR is not None and THIRD_PARTY_DIR.is_dir())
        licenses.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(THIRD_PARTY_DIR))))
        note_row = QHBoxLayout()
        note_row.addWidget(note, 1)
        note_row.addWidget(licenses)
        layout.addLayout(note_row)
        layout.addWidget(buttons)
