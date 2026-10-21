"""Corte de margens e redimensionamento de páginas de um PDF."""

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, ContentStream, FloatObject, NameObject, RectangleObject

from .base import PDFOperation, open_reader, write_pdf
from .geometry import PageGeometry, intersect_rects, normalize_rect
from .messages import Message
from .overlay import materialize_inherited_attributes

_OTHER_BOXES = ("/BleedBox", "/TrimBox", "/ArtBox")


class CropPages(PDFOperation):
    """Corta uma margem de cada lado das páginas de um PDF.

    As margens valem para a página como ela aparece na tela: "topo" é o topo que o usuário
    vê, também em páginas com `/Rotate`, e a referência é a área visível (MediaBox ∩
    CropBox), não a MediaBox inteira.
    """

    def run(
        self,
        input_path: str,
        output_path: str,
        left: float = 0,
        bottom: float = 0,
        right: float = 0,
        top: float = 0,
    ) -> None:
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)

        for index, (source_page, page) in enumerate(zip(reader.pages, writer.pages)):
            geometry = PageGeometry.from_pypdf_page(source_page)
            visual = (left, bottom, geometry.width - right, geometry.height - top)
            if visual[2] <= visual[0] or visual[3] <= visual[1]:
                raise ValueError(Message("As margens de corte excedem o tamanho da página {page}.", page=index + 1))
            box = RectangleObject(geometry.visual_rect_to_user(visual))
            page.mediabox = box
            page.cropbox = box
            _clip_other_boxes(page, box)

        write_pdf(writer, output_path)


class ScalePages(PDFOperation):
    """Redimensiona as páginas de um PDF para um novo tamanho, sem distorcer o conteúdo.

    O tamanho pedido é o da página como aparece na tela (um A4 em pé continua em pé mesmo
    numa página com `/Rotate`). O conteúdo é ampliado ou reduzido por igual nos dois
    eixos até caber, e centralizado; se a proporção for diferente, sobra margem em branco
    em vez de o conteúdo ficar esticado.
    """

    def run(self, input_path: str, output_path: str, width: float, height: float) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("A largura e a altura precisam ser maiores que zero.")
        reader = open_reader(input_path)
        writer = PdfWriter(clone_from=reader)
        materialize_inherited_attributes(writer)

        for source_page, page in zip(reader.pages, writer.pages):
            geometry = PageGeometry.from_pypdf_page(source_page)
            left, bottom, right, top = geometry.box
            target_w, target_h = (width, height) if geometry.rotation in (0, 180) else (height, width)
            factor = min(target_w / (right - left), target_h / (top - bottom))

            # Só o que estava visível deve aparecer: com a página maior que o conteúdo
            # reduzido, o que ficava escondido fora da CropBox poderia surgir na margem.
            _clip_contents(page, geometry.box)
            page.scale(factor, factor)
            center_x = (left + right) / 2 * factor
            center_y = (bottom + top) / 2 * factor
            box = RectangleObject(
                (center_x - target_w / 2, center_y - target_h / 2, center_x + target_w / 2, center_y + target_h / 2)
            )
            page.mediabox = box
            page.cropbox = box
            for key in _OTHER_BOXES:
                if key in page:
                    del page[key]

        write_pdf(writer, output_path)


def _clip_other_boxes(page, box: RectangleObject) -> None:
    """BleedBox/TrimBox/ArtBox precisam continuar dentro da nova área da página."""
    for key in _OTHER_BOXES:
        if key not in page:
            continue
        current = [float(value) for value in page[key]]
        clipped = intersect_rects(
            (min(current[0], current[2]), min(current[1], current[3]), max(current[0], current[2]), max(current[1], current[3])),
            normalize_rect(box),
        )
        if clipped is None:
            del page[key]
        else:
            page[NameObject(key)] = RectangleObject(clipped)


def _clip_contents(page, rect) -> None:
    content = page.get_contents()
    if content is None:
        return
    if not isinstance(content, ContentStream):
        content = ContentStream(content, page.pdf)
    left, bottom, right, top = rect
    content.operations.insert(
        0,
        (ArrayObject([FloatObject(left), FloatObject(bottom), FloatObject(right - left), FloatObject(top - bottom)]), b"re"),
    )
    content.operations.insert(1, ([], b"W"))
    content.operations.insert(2, ([], b"n"))
    page.replace_contents(content)
