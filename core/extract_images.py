"""Extração e substituição de imagens embutidas em arquivos PDF."""

import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PIL import Image, ImageOps
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject

from .base import EXTRACT, READ, PDFOperation, add_object, open_reader, replace_object, require_valid_page_index, write_pdf
from .messages import Message


class ExtractImages(PDFOperation):
    """Extrai as imagens embutidas nas páginas de um PDF."""

    def run(self, input_path: str, output_dir: str) -> list[str]:
        reader = open_reader(input_path, purpose=EXTRACT)
        stem = Path(input_path).stem
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for page_index, page in enumerate(reader.pages):
            for image_index, image_file in enumerate(page.images):
                suffix = Path(image_file.name).suffix or ".png"
                output_path = (
                    output_dir_path / f"{stem}_p{page_index + 1}_{image_index + 1}{suffix}"
                )
                with open(output_path, "wb") as f:
                    f.write(image_file.data)
                output_paths.append(str(output_path))

        return output_paths


@dataclass
class EmbeddedImageInfo:
    """Descrição resumida de uma imagem embutida numa página, para escolher qual substituir."""

    page_index: int
    image_index: int
    name: str
    width: int
    height: int


class ListEmbeddedImages(PDFOperation):
    """Lista as imagens embutidas em cada página de um PDF, com o índice usado por
    `ReplaceEmbeddedImage` para identificar qual delas substituir."""

    def run(self, input_path: str) -> list[EmbeddedImageInfo]:
        reader = open_reader(input_path, purpose=READ)
        result = []
        for page_index, page in enumerate(reader.pages):
            for image_index, image_file in enumerate(page.images):
                result.append(
                    EmbeddedImageInfo(
                        page_index=page_index,
                        image_index=image_index,
                        name=image_file.name,
                        width=image_file.image.width if image_file.image else 0,
                        height=image_file.image.height if image_file.image else 0,
                    )
                )
        return result


FIT_MODES = ("contain", "stretch")


@dataclass
class ReplaceImageResult:
    # Outras páginas (a partir de 0) que desenham a mesma imagem e por isso também mudaram.
    other_pages: list[int]


class ReplaceEmbeddedImage(PDFOperation):
    """Substitui uma imagem já embutida num PDF por outra, na mesma posição e no mesmo
    tamanho na página.

    - `fit="contain"` (padrão): a imagem nova cabe inteira na área da antiga sem distorcer;
      a sobra fica transparente. `fit="stretch"` estica a imagem nova para ocupar a área
      toda, como antes (uma imagem de outra proporção saía deformada).
    - Imagens gravadas dentro do conteúdo da página (inline) não podem ser substituídas; o
      erro diz isso com todas as letras.
    - Se a mesma imagem aparece em outras páginas, todas mudam (é um objeto só no arquivo);
      essas páginas voltam em `ReplaceImageResult.other_pages`, para a interface avisar.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        page_number: int,
        image_index: int,
        new_image_path: str,
        fit: str = "contain",
    ) -> ReplaceImageResult:
        if fit not in FIT_MODES:
            raise ValueError(f"Modo de ajuste inválido: {fit}")
        reader = open_reader(input_path)  # recusa PDF protegido por senha antes de clonar
        require_valid_page_index(len(reader.pages), page_number)

        writer = PdfWriter(clone_from=reader)
        images = writer.pages[page_number].images
        if not 0 <= image_index < len(images):
            raise ValueError(
                Message(
                    "A imagem {number} não existe: a página tem {count} imagem(ns).",
                    number=image_index + 1,
                    count=len(images),
                )
            )
        target = images[image_index]
        if target.indirect_reference is None:
            raise ValueError(
                "Esta imagem está gravada dentro do conteúdo da página (imagem inline) e não pode "
                "ser substituída sem reescrever a página. Use Editar texto ou a redação para cobri-la."
            )

        original = cast(DictionaryObject, target.indirect_reference.get_object())
        width, height = int(original.get("/Width", 1)), int(original.get("/Height", 1))
        with Image.open(new_image_path) as opened:
            plain_jpeg = (
                opened.format == "JPEG"
                and opened.mode in ("RGB", "L")
                and opened.getexif().get(0x0112, 1) == 1
            )
            raw_jpeg = Path(new_image_path).read_bytes() if plain_jpeg else None
            new_image = ImageOps.exif_transpose(opened)
            new_image.load()
            replacement = _image_xobject(writer, new_image, width / height, fit, original, raw_jpeg)
        replace_object(writer, target.indirect_reference, replacement)

        other_pages = [
            index
            for index, page in enumerate(writer.pages)
            if index != page_number and _draws(page, target.indirect_reference.idnum)
        ]
        write_pdf(writer, output_path)
        return ReplaceImageResult(other_pages=other_pages)


def _draws(page, idnum: int) -> bool:
    """Se a página (ou um formulário dentro dela) usa o objeto de imagem `idnum`."""
    stack = [page.get("/Resources")]
    seen: set[int] = set()
    while stack:
        resources = stack.pop()
        resources = resources.get_object() if resources is not None else None
        if not isinstance(resources, dict) or id(resources) in seen:
            continue
        seen.add(id(resources))
        xobjects = resources.get("/XObject")
        xobjects = xobjects.get_object() if xobjects is not None else {}
        for ref in xobjects.values():
            if getattr(ref, "idnum", None) == idnum:
                return True
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Form":
                stack.append(obj.get("/Resources"))
    return False


def _image_xobject(
    writer: PdfWriter, image: Image.Image, target_ratio: float, fit: str, original, raw_jpeg: bytes | None
) -> StreamObject:
    """O objeto de imagem do PDF para `image`, na proporção `target_ratio` (largura/altura)
    da área original quando `fit == "contain"`, com a transparência num /SMask. Um JPEG
    (`raw_jpeg`) que entra sem ajuste vai como está, sem recompressão."""
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    if fit == "contain" and abs(image.width / image.height - target_ratio) > 0.01:
        if image.width / image.height > target_ratio:
            canvas_size = (image.width, max(1, round(image.width / target_ratio)))
        else:
            canvas_size = (max(1, round(image.height * target_ratio)), image.height)
        canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
        canvas.paste(
            image.convert("RGBA"),
            ((canvas_size[0] - image.width) // 2, (canvas_size[1] - image.height) // 2),
        )
        image, has_alpha, raw_jpeg = canvas, True, None

    if raw_jpeg is not None and not has_alpha:
        stream = StreamObject()
        stream._data = raw_jpeg
        stream[NameObject("/Filter")] = NameObject("/DCTDecode")
    else:
        rgba = image.convert("RGBA") if has_alpha else None
        base = (rgba.convert("RGB") if rgba is not None else image.convert("L" if image.mode in ("L", "1") else "RGB"))
        stream = _flate_image(base)
        if rgba is not None:
            alpha = _flate_image(rgba.getchannel("A"))
            stream[NameObject("/SMask")] = add_object(writer, alpha)
    gray = image.mode in ("L", "LA", "1") and not has_alpha
    stream.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(image.width),
            NameObject("/Height"): NumberObject(image.height),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/ColorSpace"): NameObject("/DeviceGray" if gray else "/DeviceRGB"),
        }
    )
    for key in ("/OC", "/StructParent", "/Interpolate"):
        if key in original:
            stream[NameObject(key)] = original.raw_get(key)
    return stream


def _flate_image(image: Image.Image) -> StreamObject:
    stream = StreamObject()
    stream._data = zlib.compress(image.tobytes())
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    if image.mode == "L":
        stream.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(image.width),
                NameObject("/Height"): NumberObject(image.height),
                NameObject("/BitsPerComponent"): NumberObject(8),
                NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            }
        )
    return stream
