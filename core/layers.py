"""Camadas (Optional Content Groups / OCG) de arquivos PDF: listar e alternar a
visibilidade padrão de cada camada."""

from dataclasses import dataclass

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from .base import READ, open_reader, write_pdf
from .messages import Message


@dataclass
class LayerInfo:
    index: int
    name: str
    visible: bool


class ListLayers:
    """Lista as camadas (OCGs) de um PDF e se cada uma está visível por padrão. Um PDF sem
    camadas devolve uma lista vazia (não é um erro — a maioria dos PDFs não usa OCG)."""

    def run(self, input_path: str) -> list[LayerInfo]:
        reader = open_reader(input_path, purpose=READ)
        catalog = reader.root_object
        oc_properties_ref = catalog.get("/OCProperties")
        if oc_properties_ref is None:
            return []
        oc_properties = oc_properties_ref.get_object()

        ocg_refs = oc_properties.get("/OCGs") or []
        default_config = oc_properties.get("/D")
        default_config = default_config.get_object() if default_config is not None else {}
        on_refs = default_config.get("/ON") or []
        off_refs = default_config.get("/OFF") or []
        # /BaseState diz o estado das camadas que não estão em /ON nem em /OFF; com
        # /BaseState /OFF, antes todas apareciam como visíveis.
        base_visible = default_config.get("/BaseState") != "/OFF"

        layers = []
        for index, ocg_ref in enumerate(ocg_refs):
            ocg = ocg_ref.get_object()
            name = str(ocg.get("/Name", "")) or f"Camada {index + 1}"
            if ocg_ref in on_refs:
                visible = True
            elif ocg_ref in off_refs:
                visible = False
            else:
                visible = base_visible
            layers.append(LayerInfo(index=index, name=name, visible=visible))
        return layers


class SetLayerVisibility:
    """Define a visibilidade padrão de uma camada (OCG) de um PDF — move a referência da
    camada entre as listas `/ON` e `/OFF` da configuração padrão de conteúdo opcional
    (`/OCProperties/D`), a mesma preferência que a maioria dos leitores respeita ao abrir o
    arquivo. Não cria nem remove camadas, nem toca no conteúdo marcado das páginas."""

    def run(self, input_path: str, output_path: str, layer_index: int, visible: bool) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        catalog = writer.root_object

        oc_properties_ref = catalog.get("/OCProperties")
        if oc_properties_ref is None:
            raise ValueError("Este PDF não tem camadas (Optional Content Groups).")
        oc_properties = oc_properties_ref.get_object()

        ocg_refs = oc_properties.get("/OCGs") or []
        if not 0 <= layer_index < len(ocg_refs):
            raise ValueError(
                Message(
                    "A camada {number} não existe: o documento tem {count} camada(s).",
                    number=layer_index + 1,
                    count=len(ocg_refs),
                )
            )
        target_ref = ocg_refs[layer_index]

        default_config_ref = oc_properties.get("/D")
        if default_config_ref is None:
            default_config = DictionaryObject()
            oc_properties[NameObject("/D")] = default_config
        else:
            default_config = default_config_ref.get_object()

        on_refs = ArrayObject(ref for ref in (default_config.get("/ON") or []) if ref != target_ref)
        off_refs = ArrayObject(ref for ref in (default_config.get("/OFF") or []) if ref != target_ref)
        if visible:
            on_refs.append(target_ref)
        else:
            off_refs.append(target_ref)
        default_config[NameObject("/ON")] = on_refs
        default_config[NameObject("/OFF")] = off_refs

        write_pdf(writer, output_path)
