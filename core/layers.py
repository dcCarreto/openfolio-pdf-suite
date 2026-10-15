"""Camadas (Optional Content Groups / OCG) de arquivos PDF: listar e alternar a
visibilidade padrão de cada camada."""

from dataclasses import dataclass

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from .base import READ, PDFOperation, open_reader, write_pdf


@dataclass
class LayerInfo:
    index: int
    name: str
    visible: bool


class ListLayers(PDFOperation):
    """Lista as camadas (OCGs) de um PDF e se cada uma está visível por padrão. Um PDF sem
    camadas devolve uma lista vazia (não é um erro — a maioria dos PDFs não usa OCG)."""

    def run(self, input_path: str) -> list[LayerInfo]:
        reader = open_reader(input_path, purpose=READ)
        catalog = reader.trailer["/Root"]
        oc_properties_ref = catalog.get("/OCProperties")
        if oc_properties_ref is None:
            return []
        oc_properties = oc_properties_ref.get_object()

        ocg_refs = oc_properties.get("/OCGs") or []
        default_config_ref = oc_properties.get("/D")
        off_refs = (
            default_config_ref.get_object().get("/OFF") or [] if default_config_ref is not None else []
        )

        layers = []
        for index, ocg_ref in enumerate(ocg_refs):
            ocg = ocg_ref.get_object()
            name = str(ocg.get("/Name", "")) or f"Camada {index + 1}"
            visible = ocg_ref not in off_refs
            layers.append(LayerInfo(index=index, name=name, visible=visible))
        return layers


class SetLayerVisibility(PDFOperation):
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
                f"Índice de camada inválido: {layer_index} (o documento tem {len(ocg_refs)} "
                f"camada(s), de 0 a {len(ocg_refs) - 1})."
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
