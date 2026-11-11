"""Structured document model: IDs, immutability, JSON round trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.document import (
    Document,
    Locator,
    Paragraph,
    Table,
    TableCell,
    cell_ref,
    element_id_for,
)


def _locator(line_start: int, line_end: int) -> Locator:
    return Locator(page=9, section_path=("3", "3.2"), line_start=line_start, line_end=line_end)


def _document() -> Document:
    paragraph = Paragraph(
        element_id="e0001", locator=_locator(1, 1), raw="  계량한다.  ", text="계량한다."
    )
    table = Table(
        element_id="e0002",
        locator=_locator(3, 5),
        raw="|항목|기준|\n|---|---|\n|중량|±1.0%|",
        text="항목 | 기준\n중량 | ±1.0%",
        table_index=1,
        header=("항목", "기준"),
        rows=((TableCell(row=1, col=1, text="중량"), TableCell(row=1, col=2, text="±1.0%")),),
    )
    return Document(
        doc_id="SOP-SAMPLE",
        version="1",
        variant="source",
        language="ko",
        file_name="sample.md",
        sha256="0" * 64,
        elements=(paragraph, table),
    )


def test_element_id_is_the_position_in_four_digits():
    assert element_id_for(1) == "e0001"
    assert element_id_for(49) == "e0049"


def test_cell_ref_names_the_element_row_and_column():
    assert cell_ref("e0017", 2, 3) == "e0017:r2c3"
    assert cell_ref("e0017", 0, 1) == "e0017:r0c1"  # row 0 is the header


def test_models_are_frozen():
    document = _document()
    with pytest.raises(ValidationError):
        document.elements[0].text = "다른 문장"
    with pytest.raises(ValidationError):
        document.version = "2"


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Locator(page=1, section_path=(), line_start=1, line_end=1, bbox=(0, 0, 1, 1))


def test_document_survives_a_json_round_trip():
    document = _document()
    restored = Document.model_validate_json(document.model_dump_json())
    assert restored == document
    assert [type(element) for element in restored.elements] == [Paragraph, Table]
    assert restored.elements[1].rows[0][1].text == "±1.0%"


def test_an_element_of_unknown_kind_is_rejected():
    data = _document().model_dump()
    data["elements"][0]["kind"] = "footnote"
    with pytest.raises(ValidationError):
        Document.model_validate(data)
