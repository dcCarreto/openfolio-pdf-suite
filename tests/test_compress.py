import pytest
from pypdf import PdfReader

from core.base import EncryptedPDFError
from core.compress import CompressPDF
from core.watermark import AddWatermark


def _uncompressed_pdf(path, pages=2):
    """PDF com content streams sem compressão: comprimir sempre reduz o tamanho."""
    from reportlab.pdfgen import canvas as rl_canvas

    c = rl_canvas.Canvas(str(path), pageCompression=0)
    for page in range(pages):
        for line in range(60):
            c.drawString(40, 800 - line * 12, f"pagina {page + 1} linha {line} texto repetido " * 2)
        c.showPage()
    c.save()
    return path


def test_compress_preserves_page_count(tmp_path):
    pdf_path = _uncompressed_pdf(tmp_path / "doc.pdf")
    output_path = tmp_path / "compressed.pdf"

    result = CompressPDF().run(str(pdf_path), str(output_path))

    assert result.written and output_path.exists()
    assert result.compressed_size == output_path.stat().st_size < pdf_path.stat().st_size
    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2


def test_compress_page_with_real_content_stream(tmp_path):
    watermarked_path = tmp_path / "watermarked.pdf"
    AddWatermark().run(str(_uncompressed_pdf(tmp_path / "doc.pdf")), str(watermarked_path), text="OpenFolio")

    output_path = tmp_path / "compressed.pdf"
    CompressPDF().run(str(watermarked_path), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 2
    assert "OpenFolio" in reader.pages[0].extract_text()


def test_compress_rejects_encrypted_input(make_encrypted_pdf, tmp_path):
    encrypted_path = make_encrypted_pdf("protected.pdf", [(200, 200)])

    with pytest.raises(EncryptedPDFError):
        CompressPDF().run(str(encrypted_path), str(tmp_path / "out.pdf"))


def test_failed_operation_leaves_no_partial_file(tmp_path, monkeypatch):
    # A gravação é atômica: se der erro no meio, o destino não fica truncado.
    from pypdf import PdfWriter

    pdf_path = _uncompressed_pdf(tmp_path / "doc.pdf")
    output_path = tmp_path / "out.pdf"
    output_path.write_bytes(b"conteudo anterior")

    def broken_write(self, stream):
        stream.write(b"%PDF-1.7 pela metade")
        raise OSError("disco cheio")

    monkeypatch.setattr(PdfWriter, "write", broken_write)
    with pytest.raises(OSError):
        CompressPDF().run(str(pdf_path), str(output_path))

    assert output_path.read_bytes() == b"conteudo anterior"
    assert not list(tmp_path.glob(".openfolio-*"))


def test_output_can_be_the_input_file_itself(tmp_path):
    pdf_path = _uncompressed_pdf(tmp_path / "doc.pdf")
    original_size = pdf_path.stat().st_size

    CompressPDF().run(str(pdf_path), str(pdf_path))

    assert pdf_path.stat().st_size < original_size
    assert len(PdfReader(str(pdf_path)).pages) == 2
