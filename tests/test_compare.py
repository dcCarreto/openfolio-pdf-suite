"""Testes de core/compare.py: diff de texto e diff visual entre duas versões de um PDF."""

import pytest
from reportlab.pdfgen import canvas as rl_canvas

from core.base import EncryptedPDFError
from core.compare import CompareText, CompareVisual


def _make_pdf_with_text(path, texts: list[str], pagesize=(400, 300)) -> None:
    canvas = rl_canvas.Canvas(str(path), pagesize=pagesize)
    canvas.setFont("Helvetica", 16)
    y = pagesize[1] - 50
    for text in texts:
        canvas.drawString(40, y, text)
        y -= 40
    canvas.showPage()
    canvas.save()


def test_compare_text_detects_changed_page(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["Valor: 100"])
    _make_pdf_with_text(path_b, ["Valor: 200"])

    results = CompareText().run(str(path_a), str(path_b))

    assert len(results) == 1
    assert results[0].changed
    assert any("100" in line for line in results[0].diff_lines)
    assert any("200" in line for line in results[0].diff_lines)


def test_compare_text_reports_unchanged_page(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["Texto igual"])
    _make_pdf_with_text(path_b, ["Texto igual"])

    results = CompareText().run(str(path_a), str(path_b))

    assert len(results) == 1
    assert not results[0].changed
    assert results[0].diff_lines == []


def test_compare_text_handles_different_page_counts(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["Pagina unica"])

    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    writer.add_page(PdfReader(str(path_a)).pages[0])
    extra_path = tmp_path / "_extra.pdf"
    _make_pdf_with_text(extra_path, ["Segunda pagina"])
    writer.add_page(PdfReader(str(extra_path)).pages[0])
    with open(path_b, "wb") as f:
        writer.write(f)

    results = CompareText().run(str(path_a), str(path_b))

    assert len(results) == 2
    assert not results[0].changed
    assert results[1].changed  # página só existe em B


def test_compare_text_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_b, ["x"])

    with pytest.raises(EncryptedPDFError):
        CompareText().run(str(encrypted_path), str(path_b))


def test_compare_visual_flags_changed_and_unchanged_pages(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["Conteudo original"])
    _make_pdf_with_text(path_b, ["Conteudo bem diferente aqui"])

    output_dir = tmp_path / "diffs"
    results = CompareVisual().run(str(path_a), str(path_b), str(output_dir))

    assert len(results) == 1
    assert results[0].status == "compared"
    assert results[0].changed_fraction > 0
    assert results[0].output_path is not None
    from pathlib import Path
    assert Path(results[0].output_path).is_file()


def test_compare_visual_reports_identical_pages_as_near_zero_change(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["Texto identico"])
    _make_pdf_with_text(path_b, ["Texto identico"])

    output_dir = tmp_path / "diffs"
    results = CompareVisual().run(str(path_a), str(path_b), str(output_dir))

    assert results[0].changed_fraction == 0.0


def test_compare_visual_flags_pages_only_in_one_version(tmp_path):
    path_a = tmp_path / "a.pdf"
    _make_pdf_with_text(path_a, ["Pagina unica"])

    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    writer.add_page(PdfReader(str(path_a)).pages[0])
    extra_path = tmp_path / "_extra.pdf"
    _make_pdf_with_text(extra_path, ["Segunda pagina"])
    writer.add_page(PdfReader(str(extra_path)).pages[0])
    path_b = tmp_path / "b.pdf"
    with open(path_b, "wb") as f:
        writer.write(f)

    output_dir = tmp_path / "diffs"
    results = CompareVisual().run(str(path_a), str(path_b), str(output_dir))

    assert len(results) == 2
    assert results[0].status == "compared"
    assert results[1].status == "only_in_b"
    assert results[1].output_path is None


def test_compare_visual_flags_size_mismatch(tmp_path):
    path_a = tmp_path / "a.pdf"
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_a, ["A"], pagesize=(400, 300))
    _make_pdf_with_text(path_b, ["B"], pagesize=(200, 600))

    output_dir = tmp_path / "diffs"
    results = CompareVisual().run(str(path_a), str(path_b), str(output_dir))

    assert results[0].status == "size_mismatch"
    assert results[0].output_path is None


def test_compare_visual_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])
    path_b = tmp_path / "b.pdf"
    _make_pdf_with_text(path_b, ["x"])

    with pytest.raises(EncryptedPDFError):
        CompareVisual().run(str(encrypted_path), str(path_b), str(tmp_path / "diffs"))
