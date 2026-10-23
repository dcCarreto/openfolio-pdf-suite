"""Testes de core/layers.py: listar e alternar visibilidade de camadas (OCG)."""

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from core.base import EncryptedPDFError, add_object
from core.layers import ListLayers, SetLayerVisibility


def _make_pdf_with_layers(path, names: list[str], off: list[str] | None = None) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    off = off or []
    ocg_refs = []
    for name in names:
        ocg = DictionaryObject()
        ocg[NameObject("/Type")] = NameObject("/OCG")
        ocg[NameObject("/Name")] = TextStringObject(name)
        ocg_refs.append(add_object(writer, ocg))

    on_refs = ArrayObject(ref for ref, name in zip(ocg_refs, names) if name not in off)
    off_refs = ArrayObject(ref for ref, name in zip(ocg_refs, names) if name in off)

    default_config = DictionaryObject()
    default_config[NameObject("/ON")] = on_refs
    default_config[NameObject("/OFF")] = off_refs

    oc_properties = DictionaryObject()
    oc_properties[NameObject("/OCGs")] = ArrayObject(ocg_refs)
    oc_properties[NameObject("/D")] = default_config

    writer.root_object[NameObject("/OCProperties")] = oc_properties

    with open(path, "wb") as f:
        writer.write(f)


def _make_plain_pdf(path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_list_layers_reports_names_and_visibility(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf_with_layers(pdf_path, ["Fundo", "Anotações", "Rascunho"], off=["Rascunho"])

    layers = ListLayers().run(str(pdf_path))

    assert [(layer.name, layer.visible) for layer in layers] == [
        ("Fundo", True),
        ("Anotações", True),
        ("Rascunho", False),
    ]


def test_list_layers_returns_empty_for_pdf_without_layers(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    assert ListLayers().run(str(pdf_path)) == []


def test_list_layers_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        ListLayers().run(str(encrypted_path))


def test_set_layer_visibility_hides_a_visible_layer(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf_with_layers(pdf_path, ["Fundo", "Rascunho"])
    output_path = tmp_path / "out.pdf"

    SetLayerVisibility().run(str(pdf_path), str(output_path), layer_index=1, visible=False)

    layers = ListLayers().run(str(output_path))
    assert [(layer.name, layer.visible) for layer in layers] == [("Fundo", True), ("Rascunho", False)]


def test_set_layer_visibility_shows_a_hidden_layer(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf_with_layers(pdf_path, ["Fundo", "Rascunho"], off=["Rascunho"])
    output_path = tmp_path / "out.pdf"

    SetLayerVisibility().run(str(pdf_path), str(output_path), layer_index=1, visible=True)

    layers = ListLayers().run(str(output_path))
    assert [(layer.name, layer.visible) for layer in layers] == [("Fundo", True), ("Rascunho", True)]


def test_set_layer_visibility_rejects_invalid_index(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf_with_layers(pdf_path, ["Fundo"])

    with pytest.raises(ValueError):
        SetLayerVisibility().run(str(pdf_path), str(tmp_path / "out.pdf"), layer_index=5, visible=False)


def test_set_layer_visibility_rejects_pdf_without_layers(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_plain_pdf(pdf_path)

    with pytest.raises(ValueError):
        SetLayerVisibility().run(str(pdf_path), str(tmp_path / "out.pdf"), layer_index=0, visible=False)


def test_set_layer_visibility_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        SetLayerVisibility().run(str(encrypted_path), str(tmp_path / "out.pdf"), layer_index=0, visible=False)


def _with_base_state_off(path, visible: list[str]) -> None:
    """Camadas desligadas por padrão (/BaseState /OFF), com só `visible` em /ON."""
    writer = PdfWriter(clone_from=str(path))
    properties = writer.root_object["/OCProperties"].get_object()
    config = properties["/D"].get_object()
    refs = list(properties["/OCGs"])
    names = [str(ref.get_object()["/Name"]) for ref in refs]
    config[NameObject("/BaseState")] = NameObject("/OFF")
    config[NameObject("/ON")] = ArrayObject(ref for ref, name in zip(refs, names) if name in visible)
    config[NameObject("/OFF")] = ArrayObject()
    writer.write(str(path))


def test_layers_with_base_state_off_are_listed_as_hidden(tmp_path):
    pdf_path = tmp_path / "layers.pdf"
    _make_pdf_with_layers(pdf_path, ["Texto", "Cotas", "Rascunho"])
    _with_base_state_off(pdf_path, visible=["Texto"])

    layers = ListLayers().run(str(pdf_path))

    assert [(layer.name, layer.visible) for layer in layers] == [("Texto", True), ("Cotas", False), ("Rascunho", False)]


def test_showing_a_layer_with_base_state_off(tmp_path):
    pdf_path = tmp_path / "layers.pdf"
    _make_pdf_with_layers(pdf_path, ["Texto", "Cotas"])
    _with_base_state_off(pdf_path, visible=[])
    output = tmp_path / "out.pdf"

    SetLayerVisibility().run(str(pdf_path), str(output), layer_index=1, visible=True)

    assert [layer.visible for layer in ListLayers().run(str(output))] == [False, True]
