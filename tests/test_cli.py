"""Testes de ponta a ponta de core/cli.py (A13)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from core.cli import main

ROOT = Path(__file__).resolve().parent.parent


def _widths(path) -> list[int]:
    return [round(float(page.mediabox.width)) for page in PdfReader(str(path)).pages]


def test_merge_then_extract_rotate_and_remove(make_pdf, tmp_path, capsys):
    a = make_pdf("a.pdf", [(100, 500), (200, 500)])
    b = make_pdf("b.pdf", [(300, 500)])
    merged, extracted = tmp_path / "junto.pdf", tmp_path / "extraido.pdf"
    rotated, removed = tmp_path / "girado.pdf", tmp_path / "removido.pdf"

    assert main(["merge", str(a), str(b), "-o", str(merged)]) == 0
    assert "2 arquivos juntados" in capsys.readouterr().out
    assert _widths(merged) == [100, 200, 300]

    assert main(["extract", str(merged), "-o", str(extracted), "--paginas", "3, 1"]) == 0
    assert _widths(extracted) == [300, 100]

    assert main(["rotate", str(merged), "-o", str(rotated), "--paginas", "2-", "--angulo", "180"]) == 0
    assert [page.rotation for page in PdfReader(str(rotated)).pages] == [0, 180, 180]

    assert main(["remove", str(merged), "-o", str(removed), "--paginas", "2"]) == 0
    assert _widths(removed) == [100, 300]


def test_merge_with_pages_per_file_bookmarks_and_interleave(make_pdf, tmp_path, capsys):
    a = make_pdf("frentes.pdf", [(100, 500), (200, 500)])
    b = make_pdf("versos.pdf", [(300, 500), (400, 500)])
    chosen, interleaved = tmp_path / "escolhidas.pdf", tmp_path / "intercalado.pdf"

    assert main(["merge", str(a), str(b), "-o", str(chosen), "--paginas", "2", "--paginas", "todas", "--marcador-por-arquivo"]) == 0
    assert _widths(chosen) == [200, 300, 400]
    assert [item.title for item in PdfReader(str(chosen)).outline] == ["frentes", "versos"]

    assert main(["merge", str(a), str(b), "-o", str(interleaved), "--intercalar", "--versos-invertidos"]) == 0
    assert _widths(interleaved) == [100, 400, 200, 300]

    assert main(["merge", str(a), str(b), "-o", str(tmp_path / "x.pdf"), "--paginas", "1"]) == 1
    assert "uma vez para cada arquivo" in capsys.readouterr().err
    assert main(["merge", str(a), str(b), "-o", str(tmp_path / "x.pdf"), "--versos-invertidos"]) == 1
    assert "só vale com --intercalar" in capsys.readouterr().err


def test_split_by_ranges_size_and_blank_pages(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])

    assert main(["split", str(source), "-o", str(tmp_path / "intervalos"), "--intervalos", "3, 1; 2"]) == 0
    parts = sorted((tmp_path / "intervalos").iterdir())
    assert [_widths(p) for p in parts] == [[300, 100], [200]]

    assert main(["split", str(source), "-o", str(tmp_path / "tamanho"), "--tamanho-max", "0.0001"]) == 0
    assert "Passaram do limite" in capsys.readouterr().out  # 100 bytes: nenhuma página cabe
    assert len(list((tmp_path / "tamanho").iterdir())) == 3

    from reportlab.pdfgen import canvas as rl_canvas

    scanned = tmp_path / "lote.pdf"
    canvas = rl_canvas.Canvas(str(scanned))
    for text in ("Primeiro", "", "Segundo"):  # a do meio é a folha de separação
        if text:
            canvas.setFont("Helvetica", 40)
            canvas.drawString(100, 500, text)
        canvas.showPage()
    canvas.save()
    assert main(["split", str(scanned), "-o", str(tmp_path / "branco"), "--paginas-em-branco"]) == 0
    assert [len(PdfReader(str(p)).pages) for p in sorted((tmp_path / "branco").iterdir())] == [1, 1]

    with pytest.raises(SystemExit):  # um modo só
        main(["split", str(source), "-o", str(tmp_path / "y"), "--marcadores", "--intervalos", "1"])


def test_nothing_is_overwritten_without_force(make_pdf, tmp_path, capsys):
    a = make_pdf("a.pdf", [(100, 100)])
    existing = make_pdf("existe.pdf", [(400, 400)])

    assert main(["merge", str(a), "-o", str(existing)]) == 1
    assert "já existe" in capsys.readouterr().err
    assert _widths(existing) == [400]

    assert main(["merge", str(a), "-o", str(existing), "--force"]) == 0
    assert _widths(existing) == [100]


def test_split_and_images_need_an_empty_folder(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])
    parts = tmp_path / "partes"

    assert main(["split", str(source), "-o", str(parts), "--paginas-por-arquivo", "2"]) == 0
    assert sorted(p.name for p in parts.iterdir()) == ["doc_part1.pdf", "doc_part2.pdf"]
    assert main(["split", str(source), "-o", str(parts)]) == 1
    assert "não está vazia" in capsys.readouterr().err

    images = tmp_path / "imagens"
    assert main(["images", str(source), "-o", str(images), "--escala", "0.5", "-q"]) == 0
    assert len(list(images.glob("*.png"))) == 3
    assert capsys.readouterr().out == ""  # -q cala a mensagem final


def test_images_in_tiff_with_chosen_pages(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100), (200, 200), (300, 300)])
    images = tmp_path / "imagens"

    assert main(["images", str(source), "-o", str(images), "--formato", "tiff", "--paginas", "3, 1-2"]) == 0

    assert [p.name for p in images.iterdir()] == ["doc.tif"]
    with Image.open(images / "doc.tif") as tiff:
        assert tiff.n_frames == 3
    assert "1 imagem em" in capsys.readouterr().out


def test_info_json_is_for_scripts(make_pdf, capsys):
    source = make_pdf("doc.pdf", [(595, 842), (842, 595)])

    assert main(["info", str(source), "--json"]) == 0

    info = json.loads(capsys.readouterr().out)
    assert info["page_count"] == 2 and info["permissions"] is None
    assert [group["pages"] for group in info["page_sizes"]] == [[0], [1]]


def test_protected_pdf_asks_for_the_password_option(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100)])
    locked, unlocked, text = tmp_path / "com_senha.pdf", tmp_path / "sem_senha.pdf", tmp_path / "texto.txt"

    assert main(["protect", str(source), "-o", str(locked), "--senha-nova", "s3nha"]) == 0
    assert main(["text", str(locked), "-o", str(text)]) == 1
    assert "informe-a com --senha" in capsys.readouterr().err
    assert main(["text", str(locked), "-o", str(text), "--senha", "s3nha"]) == 0
    assert main(["rotate", str(locked), "-o", str(tmp_path / "g.pdf"), "--senha", "s3nha"]) == 1
    assert "openfolio unlock" in capsys.readouterr().err

    assert main(["unlock", str(locked), "-o", str(unlocked), "--senha", "s3nha"]) == 0
    assert not PdfReader(str(unlocked)).is_encrypted


def test_errors_are_sentences_not_tracebacks(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100)])
    broken = tmp_path / "quebrado.pdf"
    broken.write_bytes(b"isto nao e um pdf")

    assert main(["remove", str(source), "-o", str(tmp_path / "x.pdf"), "--paginas", "7"]) == 1
    assert "A página 7 não existe" in capsys.readouterr().err
    assert main(["info", str(tmp_path / "nao_existe.pdf")]) == 1
    assert "arquivo não encontrado" in capsys.readouterr().err
    assert main(["info", str(broken)]) == 1
    assert "não deu para ler o PDF" in capsys.readouterr().err
    with pytest.raises(SystemExit) as usage:
        main(["rotate", str(source)])  # falta -o
    assert usage.value.code == 2


def test_runs_as_a_module_without_loading_qt(make_pdf):
    source = make_pdf("doc.pdf", [(100, 100)])
    script = (
        "import sys; from core.cli import main; code = main(['info', sys.argv[1]]); "
        "assert 'PySide6' not in sys.modules, 'a CLI carregou o Qt'; sys.exit(code)"
    )
    # Redirecionada, a saída usa a página de código local (cp1252 no Windows); aqui, UTF-8.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-c", script, str(source)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert result.returncode == 0, result.stderr
    assert "Páginas: 1" in result.stdout


def test_compress_levels_are_the_ones_of_the_tool(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(100, 100)])

    assert main(["compress", str(source), "-o", str(tmp_path / "c.pdf"), "--nivel", "strong"]) == 0
    with pytest.raises(SystemExit):
        main(["compress", str(source), "-o", str(tmp_path / "c.pdf"), "--nivel", "high"])


def test_missing_external_program_is_a_sentence(make_pdf, tmp_path, capsys, monkeypatch):
    import core.ocr

    def no_tesseract(*_args, **_kwargs):
        raise RuntimeError("Tesseract OCR não encontrado. Instale o Tesseract para usar esta ferramenta.")

    monkeypatch.setattr(core.ocr.OCRDocument, "run", no_tesseract)
    source = make_pdf("doc.pdf", [(100, 100)])

    assert main(["ocr", str(source), "-o", str(tmp_path / "o.pdf")]) == 1
    assert "Tesseract OCR não encontrado" in capsys.readouterr().err


def test_protect_asks_the_password_twice_when_it_is_not_given(make_pdf, tmp_path, capsys, monkeypatch):
    import getpass

    source = make_pdf("doc.pdf", [(100, 100)])
    answers = iter(["abc", "abd", "abc", "abc"])
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": next(answers))

    assert main(["protect", str(source), "-o", str(tmp_path / "p.pdf")]) == 1
    assert "não conferem" in capsys.readouterr().err
    assert main(["protect", str(source), "-o", str(tmp_path / "p.pdf")]) == 0
    assert PdfReader(str(tmp_path / "p.pdf")).is_encrypted


def test_watermark_with_a_logo_on_chosen_pages(make_pdf, tmp_path, capsys):
    source = make_pdf("doc.pdf", [(300, 300)] * 3)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (40, 20), (255, 0, 0, 128)).save(logo)
    output = tmp_path / "marcado.pdf"

    assert main(["watermark", str(source), "-o", str(output), "--imagem", str(logo), "--posicao", "tile", "--paginas", "2-3"]) == 0

    assert [bool(page.images) for page in PdfReader(str(output)).pages] == [False, True, True]
    assert main(["watermark", str(source), "-o", str(tmp_path / "x.pdf")]) == 1
    assert "--texto ou --imagem" in capsys.readouterr().err


def test_number_in_roman_numerals_after_the_cover(make_pdf, tmp_path):
    source = make_pdf("doc.pdf", [(300, 300)] * 3)
    output = tmp_path / "numerado.pdf"

    assert main(["number", str(source), "-o", str(output), "--algarismos", "ROMANOS", "--pular", "1", "-q"]) == 0

    assert [page.extract_text().strip() for page in PdfReader(str(output)).pages] == ["", "I", "II"]


def test_ocr_options_reach_the_operation(make_pdf, tmp_path, monkeypatch):
    import core.ocr

    received = {}
    monkeypatch.setattr(core.ocr.OCRDocument, "run", lambda self, *args, **kwargs: received.update(kwargs) or 1)
    source = make_pdf("doc.pdf", [(100, 100)])

    assert main(["ocr", str(source), "-o", str(tmp_path / "o.pdf"), "--paginas", "refazer", "--endireitar", "-q"]) == 0

    assert (received["mode"], received["straighten"], received["detect_orientation"]) == ("redo", True, True)
