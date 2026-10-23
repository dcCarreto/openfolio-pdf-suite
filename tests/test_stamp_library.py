"""Testes de ui/stamp_library.py: biblioteca de carimbos customizados via QSettings."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings

from ui.stamp_library import StampLibrary


@pytest.fixture
def library(tmp_path) -> StampLibrary:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return StampLibrary(settings)


def test_list_stamps_starts_empty(library):
    assert library.list_stamps() == []


def test_add_and_list_stamp(library):
    library.add_stamp("Aprovado por mim", "APROVADO POR MIM", color="4caf50")

    stamps = library.list_stamps()
    assert len(stamps) == 1
    assert stamps[0].name == "Aprovado por mim"
    assert stamps[0].text == "APROVADO POR MIM"
    assert stamps[0].color == "4caf50"


def test_add_stamp_uses_default_color_when_not_given(library):
    library.add_stamp("Urgente 2", "URGENTE!!")

    assert library.list_stamps()[0].color == "f44336"


def test_add_stamp_rejects_empty_name_or_text(library):
    with pytest.raises(ValueError):
        library.add_stamp("", "texto")
    with pytest.raises(ValueError):
        library.add_stamp("nome", "")


def test_list_stamps_sorted_by_name(library):
    library.add_stamp("Zulu", "Z")
    library.add_stamp("Alfa", "A")

    names = [stamp.name for stamp in library.list_stamps()]
    assert names == ["Alfa", "Zulu"]


def test_add_stamp_overwrites_existing_name(library):
    library.add_stamp("Meu carimbo", "Texto 1")
    library.add_stamp("Meu carimbo", "Texto 2")

    stamps = library.list_stamps()
    assert len(stamps) == 1
    assert stamps[0].text == "Texto 2"


def test_remove_stamp(library):
    library.add_stamp("A", "texto A")
    library.add_stamp("B", "texto B")

    library.remove_stamp("A")

    names = [stamp.name for stamp in library.list_stamps()]
    assert names == ["B"]


def test_remove_stamp_is_a_noop_for_unknown_name(library):
    library.add_stamp("A", "texto A")

    library.remove_stamp("nao existe")

    assert len(library.list_stamps()) == 1


def test_library_persists_across_instances_sharing_the_same_settings_file(tmp_path):
    ini_path = str(tmp_path / "settings.ini")
    settings_a = QSettings(ini_path, QSettings.Format.IniFormat)
    StampLibrary(settings_a).add_stamp("Persistente", "TEXTO")

    settings_b = QSettings(ini_path, QSettings.Format.IniFormat)
    stamps = StampLibrary(settings_b).list_stamps()

    assert len(stamps) == 1
    assert stamps[0].name == "Persistente"


def test_stamp_name_with_slash_is_listed(library):
    library.add_stamp("Aprovado/RH", "APROVADO PELO RH")
    library.add_stamp(r"C:\pasta", "OUTRO")

    names = [stamp.name for stamp in library.list_stamps()]

    assert names == ["Aprovado/RH", r"C:\pasta"]
    library.remove_stamp("Aprovado/RH")
    assert [stamp.name for stamp in library.list_stamps()] == [r"C:\pasta"]


def test_stamps_saved_in_the_old_format_are_kept(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.beginGroup("custom_stamps")
    settings.setValue("Revisado/2024/text", "REVISADO")  # gravado pela versão antiga
    settings.setValue("Revisado/2024/color", "2196f3")
    settings.setValue("Simples/text", "SIMPLES")
    settings.endGroup()
    settings.sync()
    library = StampLibrary(settings)

    assert [(s.name, s.text) for s in library.list_stamps()] == [("Revisado/2024", "REVISADO"), ("Simples", "SIMPLES")]
    library.add_stamp("Novo", "NOVO")  # passa tudo para o formato novo
    assert [s.name for s in StampLibrary(settings).list_stamps()] == ["Novo", "Revisado/2024", "Simples"]
