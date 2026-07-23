import pytest
from pypdf import PdfReader

from core.create import CreateBlankPDF
from core.form_fields import AddFormField


def test_add_text_field(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    CreateBlankPDF().run(str(pdf_path), page_count=1, width=400, height=400)

    output_path = tmp_path / "with_field.pdf"
    AddFormField().run(
        str(pdf_path),
        str(output_path),
        field_name="nome",
        page_number=0,
        x=50,
        y=300,
        width=150,
        height=20,
        field_type="text",
    )

    fields = PdfReader(str(output_path)).get_fields()
    assert "nome" in fields
    assert fields["nome"]["/FT"] == "/Tx"


def test_add_checkbox_field(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    CreateBlankPDF().run(str(pdf_path), page_count=1, width=400, height=400)

    output_path = tmp_path / "with_checkbox.pdf"
    AddFormField().run(
        str(pdf_path),
        str(output_path),
        field_name="aceite",
        page_number=0,
        x=50,
        y=250,
        height=15,
        field_type="checkbox",
        checked=True,
    )

    fields = PdfReader(str(output_path)).get_fields()
    assert "aceite" in fields
    assert fields["aceite"]["/FT"] == "/Btn"


def test_add_two_fields_sequentially_keeps_both(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    CreateBlankPDF().run(str(pdf_path), page_count=1, width=400, height=400)

    step1_path = tmp_path / "step1.pdf"
    AddFormField().run(
        str(pdf_path),
        str(step1_path),
        field_name="campo1",
        page_number=0,
        x=50,
        y=300,
        field_type="text",
    )

    step2_path = tmp_path / "step2.pdf"
    AddFormField().run(
        str(step1_path),
        str(step2_path),
        field_name="campo2",
        page_number=0,
        x=50,
        y=250,
        height=15,
        field_type="checkbox",
    )

    fields = PdfReader(str(step2_path)).get_fields()
    assert set(fields.keys()) == {"campo1", "campo2"}


def test_rejects_invalid_field_type(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    CreateBlankPDF().run(str(pdf_path), page_count=1)

    with pytest.raises(ValueError):
        AddFormField().run(
            str(pdf_path),
            str(tmp_path / "out.pdf"),
            field_name="x",
            page_number=0,
            x=0,
            y=0,
            field_type="invalido",
        )
