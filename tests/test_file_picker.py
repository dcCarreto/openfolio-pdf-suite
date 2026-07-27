"""Testes de ui/widgets/file_picker.py: sugestão de nome de saída no modo "save"."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from ui.widgets.file_picker import FilePicker


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_suggested_start_path_derives_name_from_source(tmp_path):
    _app()
    source_path = str(tmp_path / "contrato.pdf")
    picker = FilePicker(mode="save", suggested_source=lambda: source_path, suggested_suffix="mesclado")

    assert picker._suggested_start_path() == str(tmp_path / "contrato_mesclado.pdf")


def test_suggested_start_path_is_empty_without_source():
    _app()
    picker = FilePicker(mode="save")

    assert picker._suggested_start_path() == ""


def test_suggested_start_path_ignores_empty_source():
    _app()
    picker = FilePicker(mode="save", suggested_source=lambda: "")

    assert picker._suggested_start_path() == ""


def test_suggested_start_path_swallows_exception_from_source():
    _app()

    def _boom():
        raise RuntimeError("nao deveria propagar")

    picker = FilePicker(mode="save", suggested_source=_boom)

    assert picker._suggested_start_path() == ""


def test_suggested_start_path_prefers_already_chosen_path_over_suggestion(tmp_path):
    _app()
    source_path = str(tmp_path / "contrato.pdf")
    chosen_path = str(tmp_path / "outra_pasta" / "escolhida.pdf")
    picker = FilePicker(mode="save", suggested_source=lambda: source_path)
    picker._path = chosen_path

    assert picker._suggested_start_path() == chosen_path


def test_browse_passes_suggested_path_to_save_dialog(monkeypatch, tmp_path):
    _app()
    source_path = str(tmp_path / "contrato.pdf")
    picker = FilePicker(mode="save", suggested_source=lambda: source_path, suggested_suffix="mesclado")

    captured = {}

    def fake_get_save_file_name(parent, caption, directory, file_filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_get_save_file_name)

    picker._browse()

    assert captured["directory"] == str(tmp_path / "contrato_mesclado.pdf")
