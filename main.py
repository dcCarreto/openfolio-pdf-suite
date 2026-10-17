"""Ponto de entrada da aplicação."""

import logging
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.app_events import FileOpenFilter, pdf_paths_from_arguments
from ui.diagnostics import install_exception_hooks, setup_logging
from ui.main_window import APP_VERSION, MainWindow
from ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    # Nomes usados pela pasta de dados (log) e pelas preferências (tamanho da janela).
    app.setOrganizationName("OpenFolio")
    app.setApplicationName("OpenFolio PDF Suite")
    app.setApplicationVersion(APP_VERSION)

    log_file = setup_logging()
    install_exception_hooks()
    logging.getLogger("openfolio").info("OpenFolio PDF Suite %s iniciado (log: %s)", APP_VERSION, log_file)

    apply_theme(app)
    window = MainWindow(settings=QSettings())
    window.show()

    # "Abrir com" / duplo clique num PDF: o arquivo chega como argumento (Windows, Linux)
    # ou como evento FileOpen (macOS).
    file_open_filter = FileOpenFilter(window.session.open)
    app.installEventFilter(file_open_filter)
    for path in pdf_paths_from_arguments(sys.argv[1:])[:1]:
        window.session.open(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
