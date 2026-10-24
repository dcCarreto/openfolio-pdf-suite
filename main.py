"""Ponto de entrada da aplicação."""

import logging
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from core.version import APP_VERSION
from ui.app_events import FileOpenFilter, pdf_paths_from_arguments
from ui.diagnostics import install_exception_hooks, setup_logging
from ui.instances import AppWindows, InstanceServer, send_to_running_instance
from ui.main_window import MainWindow
from ui.preferences import Preferences
from ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    # Nomes usados pela pasta de dados (log) e pelas preferências (tamanho da janela).
    app.setOrganizationName("OpenFolio")
    app.setApplicationName("OpenFolio PDF Suite")
    app.setApplicationVersion(APP_VERSION)

    # "Abrir com" / duplo clique num PDF: o arquivo chega como argumento (Windows, Linux)
    # ou como evento FileOpen (macOS). Com o app já aberto, é ele que abre.
    paths = pdf_paths_from_arguments(sys.argv[1:])
    if send_to_running_instance(paths):
        return

    log_file = setup_logging()
    install_exception_hooks()
    # O identificador da atualização (a data) não aparece na interface; no log, ajuda o suporte.
    logging.getLogger("openfolio").info("OpenFolio PDF Suite iniciado (atualização %s, log: %s)", APP_VERSION, log_file)

    settings = QSettings()
    preferences = Preferences(settings)
    apply_theme(app, preferences.theme())

    def make_window():
        window = MainWindow(settings=settings)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        return window

    windows = AppWindows(make_window)
    windows.open([])
    windows.windows()[0].offer_app_menu()
    if preferences.check_updates_on_start() and preferences.update_check_due():
        windows.windows()[0].check_for_updates(manual=False)

    file_open_filter = FileOpenFilter(lambda path: windows.open([path]))
    app.installEventFilter(file_open_filter)
    _server = InstanceServer(windows.open)  # vive até o app fechar
    windows.open(paths)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
