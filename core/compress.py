"""Compressão de arquivos PDF.

Num PDF escaneado ou cheio de fotos, quase todo o tamanho está nas imagens; recomprimir só
os content streams (o que esta ferramenta fazia antes) deixava um escaneado de 20 MB com
os mesmos 20 MB. Agora há três níveis:

- `light`: sem perda. Recomprime os content streams, comprime imagens gravadas sem filtro
  e remove objetos repetidos ou sem uso.
- `medium` e `strong`: além disso, reamostram cada imagem para o DPI alvo (150 ou 100) —
  medido pelo tamanho com que a imagem aparece na página, não pelo tamanho da página — e a
  regravam em JPEG. Imagens coloridas que na prática são cinza (um escaneado de documento
  em preto e branco gravado em RGB) passam a ser gravadas em escala de cinza. Miniaturas de
  página (`/Thumb`) e dados privados de aplicativos (`/PieceInfo`) saem.

Cada imagem só é trocada se a versão nova ficar menor. Imagens de 1 bit (fax, JBIG2),
máscaras, imagens com `/Decode` ou máscara de cor e CMYK ficam como estão: o JPEG as
estragaria ou aumentaria. A transparência (`/SMask`) é mantida.

Com o Ghostscript instalado, `use_ghostscript=True` passa o arquivo pelo `pdfwrite` dele,
que comprime mais (fontes, por exemplo), mas pode descartar anexos, campos de formulário e
a marcação de acessibilidade — por isso é opcional.

O resultado só é gravado se o arquivo ficar menor que o original (`CompressionResult`).
"""

import io
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    EncodedStreamObject,
    IndirectObject,
    NameObject,
    NumberObject,
    StreamObject,
)

from .base import PDFOperation, atomic_output, open_reader, replace_object
from .external import find_ghostscript, run_cancellable
from .messages import Message
from .progress import Progress, ensure_progress

LEVELS = ("light", "medium", "strong")

# DPI alvo e qualidade JPEG por nível (None = sem reamostragem nem perda).
_LEVEL_SETTINGS = {
    "light": None,
    "medium": (150, 75),
    "strong": (100, 55),
}
_GHOSTSCRIPT_SETTINGS = {"light": "/printer", "medium": "/ebook", "strong": "/screen"}

_MIN_IMAGE_SIDE = 16  # ícones e fios: não vale a pena
_GRAY_TOLERANCE = 6  # diferença máxima entre canais para tratar a imagem como cinza
_GHOSTSCRIPT_TIMEOUT = 600  # segundos

@dataclass
class CompressionResult:
    original_size: int
    compressed_size: int
    images_recompressed: int = 0
    used_ghostscript: bool = False
    written: bool = True  # False: o resultado não ficou menor e nada foi gravado

    @property
    def reduction_percent(self) -> float:
        if not self.original_size:
            return 0.0
        return 100 * (1 - self.compressed_size / self.original_size)


class CompressPDF(PDFOperation):
    """Reduz o tamanho de um PDF (ver os níveis no docstring do módulo). Trabalha sobre uma
    cópia completa do documento: marcadores, formulário, anexos e metadados continuam lá."""

    def run(
        self,
        input_path: str,
        output_path: str,
        level: str = "medium",
        grayscale: bool = False,
        use_ghostscript: bool = False,
        progress: Progress | None = None,
    ) -> CompressionResult:
        progress = ensure_progress(progress)
        if level not in LEVELS:
            raise ValueError(f"Nível de compressão inválido: {level} (use light, medium ou strong).")
        reader = open_reader(input_path)
        original_size = os.path.getsize(input_path)

        writer = PdfWriter(clone_from=reader)
        images_recompressed = _recompress_images(writer, level, grayscale, progress)

        for page in progress.steps(writer.pages, len(writer.pages), "Comprimindo páginas"):
            page.compress_content_streams()
            if level != "light":
                for key in ("/Thumb", "/PieceInfo"):
                    if key in page:
                        del page[NameObject(key)]
        if level != "light" and "/PieceInfo" in writer.root_object:
            del writer.root_object[NameObject("/PieceInfo")]

        progress.update(0, 0, "Removendo objetos repetidos")
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        progress.check()

        buffer = io.BytesIO()
        writer.write(buffer)
        data = buffer.getvalue()

        used_ghostscript = False
        if use_ghostscript:
            gs_path = find_ghostscript()
            if not gs_path:
                raise RuntimeError("Ghostscript não encontrado. Instale o Ghostscript ou desmarque a opção.")
            progress.update(0, 0, "Comprimindo com o Ghostscript")
            gs_data = _ghostscript_compress(gs_path, data, level, grayscale, progress)
            if len(gs_data) < len(data):
                data, used_ghostscript = gs_data, True

        result = CompressionResult(
            original_size=original_size,
            compressed_size=len(data),
            images_recompressed=images_recompressed,
            used_ghostscript=used_ghostscript,
            written=len(data) < original_size,
        )
        if result.written:
            progress.check()
            with atomic_output(output_path) as temp_path:
                Path(temp_path).write_bytes(data)
        return result


# --- Imagens ---------------------------------------------------------------------------


def _recompress_images(writer: PdfWriter, level: str, grayscale: bool, progress: Progress) -> int:
    settings = _LEVEL_SETTINGS[level]
    display_sizes: dict[int, tuple[float, float]] = {}  # idnum -> maior tamanho exibido (pt)
    images: dict[int, IndirectObject] = {}
    for page in writer.pages:
        _collect_image_uses(page.get_contents(), page.get("/Resources"), (1, 0, 0, 1, 0, 0), display_sizes, images, set())

    page_width, page_height = _largest_page(writer)
    replaced = 0
    for ref in progress.steps(list(images.values()), message="Comprimindo imagens"):
        image_obj = ref.get_object()
        width_pt, height_pt = display_sizes.get(ref.idnum, (page_width, page_height))
        new_obj = _recompressed_image(image_obj, settings, grayscale, width_pt, height_pt)
        if new_obj is not None:
            replace_object(writer, ref, new_obj)
            replaced += 1
    return replaced


def _largest_page(writer: PdfWriter) -> tuple[float, float]:
    widths = [float(page.mediabox.width) for page in writer.pages] or [612.0]
    heights = [float(page.mediabox.height) for page in writer.pages] or [792.0]
    return max(widths), max(heights)


def _multiply(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def _collect_image_uses(contents, resources, ctm, display_sizes, images, visited_forms) -> None:
    """Percorre um content stream (e os Form XObjects que ele desenha) registrando, para
    cada imagem, o maior tamanho com que ela aparece — é o que define o DPI efetivo."""
    if contents is None or resources is None:
        return
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    xobjects = xobjects.get_object() if xobjects is not None else {}
    try:
        operations = ContentStream(contents, None).operations
    except Exception:
        operations = []

    stack = []
    for operands, operator in operations:
        if operator == b"q":
            stack.append(ctm)
        elif operator == b"Q":
            ctm = stack.pop() if stack else ctm
        elif operator == b"cm" and len(operands) == 6:
            ctm = _multiply(tuple(float(v) for v in operands), ctm)
        elif operator == b"Do" and operands:
            ref = xobjects.get(operands[0]) if hasattr(xobjects, "get") else None
            if not isinstance(ref, IndirectObject):
                continue
            xobject = ref.get_object()
            subtype = xobject.get("/Subtype")
            if subtype == "/Image":
                a, b, c, d, _e, _f = ctm
                size = (math.hypot(a, b), math.hypot(c, d))
                previous = display_sizes.get(ref.idnum, (0.0, 0.0))
                display_sizes[ref.idnum] = (max(previous[0], size[0]), max(previous[1], size[1]))
                images[ref.idnum] = ref
            elif subtype == "/Form" and ref.idnum not in visited_forms:
                matrix = tuple(float(v) for v in xobject.get("/Matrix", (1, 0, 0, 1, 0, 0)))
                _collect_image_uses(
                    xobject,
                    xobject.get("/Resources", resources),
                    _multiply(matrix, ctm),
                    display_sizes,
                    images,
                    visited_forms | {ref.idnum},
                )


def _filters(image_obj) -> list[str]:
    filters = image_obj.get("/Filter")
    if filters is None:
        return []
    filters = filters.get_object()
    if isinstance(filters, ArrayObject):
        return [str(f) for f in filters]
    return [str(filters)]


def _recompressed_image(image_obj, settings, grayscale: bool, width_pt: float, height_pt: float):
    """A imagem regravada (StreamObject), ou None se não houver ganho ou se mexer nela não
    for seguro."""
    if image_obj.get("/ImageMask") or "/Decode" in image_obj:
        return None
    if isinstance(image_obj.get("/Mask"), ArrayObject):
        return None  # máscara por faixa de cor: o JPEG mudaria as cores e a máscara erraria
    if int(image_obj.get("/BitsPerComponent", 8)) != 8:
        return None
    filters = _filters(image_obj)
    if any(f in ("/JBIG2Decode", "/CCITTFaxDecode", "/JPXDecode") for f in filters):
        return None
    width, height = int(image_obj.get("/Width", 0)), int(image_obj.get("/Height", 0))
    if min(width, height) < _MIN_IMAGE_SIDE:
        return None
    colorspace = image_obj.get("/ColorSpace")
    colorspace = colorspace.get_object() if colorspace is not None else None
    if colorspace == "/DeviceCMYK" or (isinstance(colorspace, ArrayObject) and colorspace and colorspace[0] == "/DeviceN"):
        return None

    original_length = len(image_obj._data) if getattr(image_obj, "_data", None) is not None else 0

    if settings is None:
        # Sem perda: só comprime o que está gravado cru.
        if filters:
            return None
        raw = image_obj.get_data()
        new_obj = StreamObject()
        new_obj.update({key: value for key, value in image_obj.items() if key not in ("/Filter", "/DecodeParms", "/Length")})
        new_obj.set_data(raw)
        new_obj = new_obj.flate_encode()
        return new_obj if len(new_obj._data) < len(raw) else None

    target_dpi, quality = settings
    try:
        image = _decode(image_obj)
    except Exception:
        return None
    if image is None:
        return None

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if image.mode == "RGB" and (grayscale or _is_gray(image)):
        image = image.convert("L")

    scale = _downsample_scale(width, height, width_pt, height_pt, target_dpi)
    if scale < 1:
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    elif "/DCTDecode" in filters and image.mode == ("L" if colorspace == "/DeviceGray" else "RGB"):
        return None  # já é JPEG no tamanho certo: regravar só perderia qualidade

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    jpeg = buffer.getvalue()
    if original_length and len(jpeg) >= original_length:
        return None

    new_obj = StreamObject()
    new_obj._data = jpeg
    new_obj.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(image.width),
            NameObject("/Height"): NumberObject(image.height),
            NameObject("/ColorSpace"): NameObject("/DeviceGray" if image.mode == "L" else "/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Filter"): NameObject("/DCTDecode"),
        }
    )
    for key in ("/SMask", "/Mask", "/Interpolate", "/Intent", "/OC", "/Metadata", "/StructParent"):
        if key in image_obj:
            new_obj[NameObject(key)] = image_obj.raw_get(key)
    return new_obj


def _decode(image_obj) -> Image.Image | None:
    from pypdf.generic._image_xobject import _xobj_to_image

    # Sem a máscara: a transparência continua no /SMask original, que é mantido.
    stream = EncodedStreamObject()
    stream.update({key: value for key, value in image_obj.items() if key not in ("/SMask", "/Mask")})
    stream._data = image_obj._data
    _extension, _data, image = _xobj_to_image(stream)
    return image


def _is_gray(image: Image.Image) -> bool:
    sample = image.copy()
    sample.thumbnail((256, 256))
    red, green, blue = sample.split()
    for a, b in ((red, green), (green, blue)):
        low, high = ImageChops.difference(a, b).getextrema()
        if high > _GRAY_TOLERANCE:
            return False
    return True


def _downsample_scale(width: int, height: int, width_pt: float, height_pt: float, target_dpi: int) -> float:
    """Fator de redução para que a imagem fique com `target_dpi` no maior tamanho em que
    aparece. Só reduz quando passa de 1,5x o alvo (como o Acrobat), para não estragar
    imagens que já estão perto do alvo."""
    if width_pt <= 0 or height_pt <= 0:
        return 1.0
    dpi = min(width / (width_pt / 72), height / (height_pt / 72))
    if dpi <= target_dpi * 1.5:
        return 1.0
    return target_dpi / dpi


# --- Ghostscript -----------------------------------------------------------------------


def _ghostscript_compress(gs_path: str, data: bytes, level: str, grayscale: bool, progress: Progress) -> bytes:
    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "in.pdf"
        target = Path(tmp_dir) / "out.pdf"
        source.write_bytes(data)
        command = [
            gs_path,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-dPDFSETTINGS={_GHOSTSCRIPT_SETTINGS[level]}",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            "-dSAFER",
            f"-sOutputFile={target}",
        ]
        if grayscale:
            command += ["-sColorConversionStrategy=Gray", "-dProcessColorModel=/DeviceGray"]
        command.append(str(source))

        returncode, stderr = run_cancellable(command, progress, _GHOSTSCRIPT_TIMEOUT, program="O Ghostscript")
        if returncode != 0 or not target.is_file():
            detail = stderr.decode(errors="replace").strip() or f"código de saída {returncode}"
            raise RuntimeError(Message("O Ghostscript falhou ao comprimir o arquivo: {detail}", detail=detail))
        return target.read_bytes()
