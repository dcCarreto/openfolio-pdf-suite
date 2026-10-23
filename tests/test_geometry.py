"""Testes de core/geometry.py: conversão entre espaço do usuário, espaço visual e tela.

Além das contas em si, os testes usam o próprio pdfium como referência (FPDF_PageToDevice e
a posição real dos pixels renderizados): a geometria precisa bater com o que o visualizador
mostra, não só ser coerente consigo mesma.
"""

import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas as rl_canvas

from core.geometry import PageGeometry, intersect_rects, normalize_rect, normalize_rotation
from tests.conftest import HARD_PAGE_LAYOUTS

_LAYOUTS = list(HARD_PAGE_LAYOUTS.items())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0), (90, 90), (180, 180), (270, 270), (360, 0), (450, 90), (-90, 270), (-180, 180), (45, 0)],
)
def test_normalize_rotation_matches_pdfium(raw, expected):
    assert normalize_rotation(raw) == expected


def test_normalize_rect_orders_coordinates():
    assert normalize_rect((100, 50, 10, 5)) == (10.0, 5.0, 100.0, 50.0)


def test_intersect_rects():
    assert intersect_rects((0, 0, 10, 10), (5, 5, 20, 20)) == (5, 5, 10, 10)
    assert intersect_rects((0, 0, 10, 10), (20, 20, 30, 30)) is None


def test_cropbox_is_intersected_with_mediabox():
    geometry = PageGeometry.from_boxes((0, 0, 612, 792), (-10, 200, 700, 792))
    assert geometry.box == (0, 200, 612, 792)
    assert (geometry.width, geometry.height) == (612, 592)


def test_cropbox_outside_mediabox_falls_back_to_mediabox():
    geometry = PageGeometry.from_boxes((0, 0, 612, 792), (1000, 1000, 1100, 1100))
    assert geometry.box == (0, 0, 612, 792)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_visual_size_swaps_on_quarter_turns(rotation):
    geometry = PageGeometry.from_boxes((50, 100, 650, 900), rotation=rotation)
    if rotation in (90, 270):
        assert (geometry.width, geometry.height) == (800, 600)
    else:
        assert (geometry.width, geometry.height) == (600, 800)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_user_visual_round_trip_and_matrix(rotation):
    geometry = PageGeometry.from_boxes((50, 100, 650, 900), rotation=rotation)
    a, b, c, d, e, f = geometry.visual_to_user_matrix()

    for x, y in [(50, 100), (650, 900), (123.5, 456.25), (600, 120)]:
        vx, vy = geometry.user_to_visual(x, y)
        assert 0 <= vx <= geometry.width and 0 <= vy <= geometry.height
        assert geometry.visual_to_user(vx, vy) == pytest.approx((x, y))
        # A matriz (usada para desenhar "de pé" em páginas giradas) faz a mesma conversão.
        assert (a * vx + c * vy + e, b * vx + d * vy + f) == pytest.approx((x, y))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_screen_round_trip(rotation):
    geometry = PageGeometry.from_boxes((50, 100, 650, 900), rotation=rotation)
    for scale in (0.5, 1.2, 4.1666):
        px, py = geometry.user_to_screen(300, 400, scale)
        assert geometry.screen_to_user(px, py, scale) == pytest.approx((300, 400))


def test_rect_conversions_keep_area():
    geometry = PageGeometry.from_boxes((0, 0, 612, 792), rotation=90)
    visual = geometry.user_rect_to_visual((100, 200, 300, 250))
    assert (visual[2] - visual[0], visual[3] - visual[1]) == pytest.approx((50, 200))
    assert geometry.visual_rect_to_user(visual) == pytest.approx((100, 200, 300, 250))


def test_clip_user_rect_to_visible_area():
    geometry = PageGeometry.from_boxes((0, 0, 612, 792), (0, 200, 612, 792))
    assert geometry.clip_user_rect((10, 100, 50, 300)) == (10, 200, 50, 300)
    assert geometry.clip_user_rect((10, 0, 50, 100)) is None


def test_visual_rect_to_pixels_rounds_outward_and_clamps():
    geometry = PageGeometry.from_boxes((0, 0, 100, 100))
    # 10x10 px por ponto: 1.25pt -> 12.5px precisa virar 12 (início) e 13 (fim), nunca menos.
    assert geometry.visual_rect_to_pixels((1.25, 1.25, 2.25, 2.25), 1000, 1000) == (12, 977, 23, 988)
    assert geometry.visual_rect_to_pixels((-5, -5, 200, 200), 1000, 1000) == (0, 0, 1000, 1000)


# -- conferência contra o pdfium ------------------------------------------------------------


def _layout_pdf(tmp_path, layout: dict, squares: list[tuple[float, float, float]] = ()):
    """PDF de uma página com quadrados pretos (x, y, lado) no espaço do usuário."""
    source = tmp_path / "_src.pdf"
    canvas = rl_canvas.Canvas(str(source), pagesize=(612, 792))
    for x, y, size in squares:
        canvas.rect(x, y, size, size, fill=1, stroke=0)
    canvas.showPage()
    canvas.save()

    writer = PdfWriter(clone_from=str(source))
    page = writer.pages[0]
    if "mediabox" in layout:
        page.mediabox = RectangleObject(layout["mediabox"])
    if "cropbox" in layout:
        page.cropbox = RectangleObject(layout["cropbox"])
    if layout.get("rotate"):
        page.rotate(layout["rotate"])
    path = tmp_path / "layout.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


@pytest.mark.parametrize(("name", "layout"), _LAYOUTS)
def test_pypdf_and_pdfium_agree_on_geometry(tmp_path, name, layout):
    path = _layout_pdf(tmp_path, layout)

    from_pypdf = PageGeometry.from_pypdf_page(PdfReader(str(path)).pages[0])
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        from_pdfium = PageGeometry.from_pdfium_page(page)
        assert from_pdfium.box == pytest.approx(from_pypdf.box)
        assert from_pdfium.rotation == from_pypdf.rotation
        assert (from_pdfium.width, from_pdfium.height) == pytest.approx(page.get_size())
    finally:
        document.close()


@pytest.mark.parametrize(("name", "layout"), _LAYOUTS)
def test_user_to_screen_matches_pdfium_page_to_device(tmp_path, name, layout):
    path = _layout_pdf(tmp_path, layout)
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        geometry = PageGeometry.from_pdfium_page(page)
        size_x, size_y = round(geometry.width * 10), round(geometry.height * 10)
        left, bottom, right, top = geometry.box
        points = [(left, bottom), (right, top), ((left + right) / 2, bottom + 37.5), (left + 11, top - 3)]

        for x, y in points:
            device_x, device_y = ctypes.c_int(), ctypes.c_int()
            ok = pdfium_c.FPDF_PageToDevice(page, 0, 0, size_x, size_y, 0, x, y, device_x, device_y)
            assert ok
            vx, vy = geometry.user_to_visual(x, y)
            expected = (vx * size_x / geometry.width, (geometry.height - vy) * size_y / geometry.height)
            assert (device_x.value, device_y.value) == pytest.approx(expected, abs=1)
    finally:
        document.close()


@pytest.mark.parametrize(("name", "layout"), _LAYOUTS)
def test_rendered_square_lands_where_geometry_says(tmp_path, name, layout):
    square = (300.0, 400.0, 30.0)  # dentro da área visível de todos os layouts
    path = _layout_pdf(tmp_path, layout, squares=[square])
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        geometry = PageGeometry.from_pdfium_page(page)
        scale = 2.0
        image = page.render(scale=scale).to_pil().convert("L")
    finally:
        document.close()

    dark = image.point(lambda value: 255 if value < 128 else 0)
    found = dark.getbbox()  # (x0, y0, x1, y1) dos pixels escuros
    x, y, size = square
    expected = geometry.user_rect_to_screen((x, y, x + size, y + size), scale)
    assert found is not None
    assert found[0] == pytest.approx(expected[0], abs=2)
    assert found[1] == pytest.approx(expected[1], abs=2)
    assert found[2] == pytest.approx(expected[0] + expected[2], abs=2)
    assert found[3] == pytest.approx(expected[1] + expected[3], abs=2)
