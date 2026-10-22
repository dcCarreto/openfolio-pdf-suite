"""Montagem de documentos a partir de páginas de outros, sem perder o que vive fora delas.

Num PDF, muito do que o usuário considera "o documento" não está nas páginas: marcadores,
metadados (título, autor e o XMP), anexos, rótulos de página ("i, ii, iii, 1, 2..."),
camadas, campos de formulário, idioma. Copiar só as páginas para um `PdfWriter()` novo
descarta tudo isso — era o que quase todas as operações faziam.

Quando a operação altera páginas no lugar (marca d'água, compressão, proteção...), o
caminho é clonar o documento inteiro (`PdfWriter(clone_from=reader)`). Quando ela muda
quais páginas existem ou a ordem delas (remover, reordenar, inserir, substituir, mesclar,
dividir), clonar não basta: as páginas removidas continuariam no arquivo, referenciadas por
marcadores, links e campos. `pages_writer` usa o `append` do pypdf — que já filtra
marcadores, destinos, links e campos de formulário para as páginas incluídas — e completa
com o que o `append` não leva.

A árvore de estrutura (tags de acessibilidade) não é levada nessas operações: ela aponta
para o conteúdo de cada página pelo número da página na árvore, que muda; copiá-la sem
reconstruir essas referências deixaria tags quebradas, ou puxaria de volta páginas
removidas. Por isso o `/MarkInfo` também não é levado — declarar "tagueado" sem tags seria
pior do que não declarar.
"""

from collections.abc import Iterator
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

# Entradas do catálogo copiadas como estão (não dependem de quais páginas existem).
_CATALOG_KEYS_TO_COPY = ("/Lang", "/ViewerPreferences", "/PageLayout", "/PageMode", "/URI")
_PAGE_LABEL_STYLES = {"/D", "/R", "/r", "/A", "/a"}


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


# -- árvores de nomes e de números -----------------------------------------------------------


def iter_name_tree(node, key: str = "/Names") -> Iterator[tuple[Any, Any]]:
    """Percorre uma árvore de nomes (ou de números, com `key="/Nums"`) do PDF, com todos os
    níveis de `/Kids`, e devolve os pares (chave, valor) — o valor como está no arquivo
    (normalmente uma referência indireta)."""
    visited: set[int] = set()
    stack = [node]
    while stack:
        current = _resolve(stack.pop())
        if not isinstance(current, DictionaryObject) or id(current) in visited:
            continue
        visited.add(id(current))
        entries = _resolve(current.get(key)) or []
        for index in range(0, len(entries) - 1, 2):
            yield _resolve(entries[index]), entries[index + 1]
        kids = _resolve(current.get("/Kids")) or []
        stack.extend(reversed(list(kids)))


def build_name_tree(pairs: list[tuple[str, object]]) -> DictionaryObject:
    """Árvore de nomes de um nível só, com as chaves em ordem (exigência do formato)."""
    names = ArrayObject()
    for key, value in sorted(pairs, key=lambda pair: pair[0]):
        names.append(TextStringObject(key))
        names.append(value)
    return DictionaryObject({NameObject("/Names"): names})


# -- rótulos de página -----------------------------------------------------------------------

PageLabel = tuple[str | None, str, int]  # (estilo, prefixo, número)


def page_label_specs(reader: PdfReader) -> list[PageLabel] | None:
    """Rótulo de cada página do documento, como (estilo, prefixo, número), ou None se o
    documento não define rótulos (aí cada leitor mostra 1, 2, 3...)."""
    labels = _resolve(reader.root_object.get("/PageLabels"))
    if not isinstance(labels, DictionaryObject):
        return None
    ranges = sorted(
        (int(start), _resolve(spec))
        for start, spec in iter_name_tree(labels, key="/Nums")
        if isinstance(_resolve(spec), DictionaryObject)
    )
    if not ranges:
        return None

    specs: list[PageLabel] = []
    current = 0
    for page_index in range(len(reader.pages)):
        while current + 1 < len(ranges) and ranges[current + 1][0] <= page_index:
            current += 1
        start, spec = ranges[current]
        if start > page_index:  # páginas antes do primeiro intervalo: numeração decimal
            specs.append(("/D", "", page_index + 1))
            continue
        style = spec.get("/S")
        style = str(style) if style in _PAGE_LABEL_STYLES else None
        prefix = str(spec.get("/P", "") or "")
        first_value = int(spec.get("/St", 1) or 1)
        specs.append((style, prefix, first_value + page_index - start))
    return specs


def apply_page_labels(writer: PdfWriter, specs: list[PageLabel | None]) -> None:
    """Define os rótulos das páginas do `writer`, uma entrada por página (None = sem rótulo
    próprio: numeração decimal pela posição). Páginas seguidas com o mesmo estilo e prefixo
    e números consecutivos viram um único intervalo."""
    if all(spec is None for spec in specs):
        return
    resolved = [spec if spec is not None else ("/D", "", index + 1) for index, spec in enumerate(specs)]

    run_start = 0
    for index in range(1, len(resolved) + 1):
        if index < len(resolved):
            previous, current = resolved[index - 1], resolved[index]
            if current[0] == previous[0] and current[1] == previous[1] and current[2] == previous[2] + 1:
                continue
        style, prefix, value = resolved[run_start]
        if style is None and not prefix:
            style = "/D"  # o pypdf exige estilo ou prefixo; um rótulo vazio vira decimal
        # PageLabelStyle é só uma classe de constantes ("/D"); o pypdf recebe o texto
        writer.set_page_label(
            run_start, index - 1, style=style, prefix=prefix or None, start=max(1, value)  # type: ignore[arg-type]
        )
        run_start = index


# -- montagem do documento -------------------------------------------------------------------


def pages_writer(
    parts: list[tuple[PdfReader, list[int]]],
    *,
    properties_from: PdfReader | None = None,
    copy_attachments: bool = True,
    titles: list[str | None] | None = None,
) -> PdfWriter:
    """Monta um documento com as páginas indicadas de cada leitor, na ordem dada.

    Os metadados, o XMP, o idioma e as preferências de exibição vêm de `properties_from`
    (por padrão, o primeiro documento); camadas e anexos (se `copy_attachments`) vêm de
    todos os documentos usados; os rótulos de página acompanham cada página de origem.
    Um título em `titles` (um por parte) vira um marcador na primeira página da parte, com os
    marcadores dela dentro.
    """
    writer = PdfWriter()
    labels: list[PageLabel | None] = []
    readers: list[PdfReader] = []
    label_cache: dict[int, list[PageLabel] | None] = {}
    for (reader, indices), title in zip(parts, titles or [None] * len(parts)):
        indices = list(indices)
        if not indices:
            continue
        writer.append(reader, outline_item=title, pages=indices)
        if id(reader) not in label_cache:
            label_cache[id(reader)] = page_label_specs(reader)
        specs = label_cache[id(reader)]
        labels.extend(specs[index] if specs else None for index in indices)
        if all(reader is not seen for seen in readers):
            readers.append(reader)

    source = properties_from or (readers[0] if readers else None)
    if source is not None:
        _copy_document_properties(writer, source)
    if readers:
        _merge_optional_content(writer, readers)
        if copy_attachments:
            _copy_embedded_files(writer, readers)
    apply_page_labels(writer, labels)
    return writer


def _copy_document_properties(writer: PdfWriter, reader: PdfReader) -> None:
    if reader.metadata:
        writer.add_metadata(
            {key: value for key, value in reader.metadata.items() if key != "/Producer"}
        )
    root = reader.root_object
    if "/Metadata" in root:
        writer.root_object[NameObject("/Metadata")] = root.raw_get("/Metadata").clone(writer)
    for key in _CATALOG_KEYS_TO_COPY:
        if key in root:
            writer.root_object[NameObject(key)] = root.raw_get(key).clone(writer)


def _merge_optional_content(writer: PdfWriter, readers: list[PdfReader]) -> None:
    """Leva as camadas (OCGs). Sem o `/OCProperties` no catálogo, os leitores ignoram as
    marcações de camada das páginas — e conteúdo de camadas ocultas passa a aparecer."""
    merged: DictionaryObject | None = None
    for reader in readers:
        if "/OCProperties" not in reader.root_object:
            continue
        cloned_ref = reader.root_object.raw_get("/OCProperties").clone(writer)
        cloned = _resolve(cloned_ref)
        if merged is None:
            merged = cloned
            writer.root_object[NameObject("/OCProperties")] = cloned_ref
            continue
        _extend_unique(merged, cloned, "/OCGs")
        target_config = _resolve(merged.get("/D"))
        source_config = _resolve(cloned.get("/D"))
        if isinstance(target_config, DictionaryObject) and isinstance(source_config, DictionaryObject):
            for key in ("/ON", "/OFF", "/Order"):
                _extend_unique(target_config, source_config, key)


def _extend_unique(target: DictionaryObject, source: DictionaryObject, key: str) -> None:
    if key not in source:
        return
    items = _resolve(target.get(key))
    if not isinstance(items, ArrayObject):
        items = ArrayObject()
        target[NameObject(key)] = items
    for item in _resolve(source[key]):
        if item not in items:
            items.append(item)


def _copy_embedded_files(writer: PdfWriter, readers: list[PdfReader]) -> None:
    pairs: list[tuple[str, object]] = []
    used: set[str] = set()
    for reader in readers:
        names = _resolve(reader.root_object.get("/Names"))
        if not isinstance(names, DictionaryObject) or "/EmbeddedFiles" not in names:
            continue
        for key, filespec in iter_name_tree(names.raw_get("/EmbeddedFiles")):
            name = unique_name(str(key), used)
            pairs.append((name, filespec.clone(writer)))
    if not pairs:
        return
    root = writer.root_object
    names = _resolve(root.get("/Names"))
    if not isinstance(names, DictionaryObject):
        names = DictionaryObject()
        root[NameObject("/Names")] = names
    names[NameObject("/EmbeddedFiles")] = build_name_tree(pairs)


def remove_widgets_from_form(writer: PdfWriter, widgets) -> None:
    """Tira da árvore de campos (`/AcroForm/Fields`) os widgets indicados — e os campos
    que ficarem sem nenhum widget. Usado quando uma página vira imagem: os campos dela
    deixam de existir, e o formulário não pode continuar apontando para eles."""
    acroform = _resolve(writer.root_object.get("/AcroForm"))
    if not isinstance(acroform, DictionaryObject) or "/Fields" not in acroform:
        return
    doomed = {id(_resolve(widget)) for widget in widgets}
    if not doomed:
        return

    def prune(items) -> ArrayObject:
        kept = ArrayObject()
        for ref in items:
            field = _resolve(ref)
            if not isinstance(field, DictionaryObject) or id(field) in doomed:
                continue
            if "/Kids" in field:
                kids = prune(_resolve(field["/Kids"]))
                if not kids:
                    continue  # campo sem nenhum widget restante
                field[NameObject("/Kids")] = kids
            kept.append(ref)
        return kept

    acroform[NameObject("/Fields")] = prune(_resolve(acroform["/Fields"]))


def unique_name(name: str, used: set[str]) -> str:
    """`name`, ou `name (2)`, `name (3)`... se já estiver em `used` (que é atualizado)."""
    stem, dot, extension = name.rpartition(".")
    if not stem:
        stem, dot, extension = name, "", ""
    candidate = name
    counter = 2
    while candidate in used:
        candidate = f"{stem} ({counter}){dot}{extension}"
        counter += 1
    used.add(candidate)
    return candidate
