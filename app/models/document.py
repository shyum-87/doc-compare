"""Structured document model: a flat, ordered list of elements with locators."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["ko", "vi", "en", "zh"]
Variant = Literal["translated", "source"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Locator(FrozenModel):
    page: Optional[int]
    section_path: tuple[str, ...]
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _lines_are_in_order(self) -> Locator:
        if self.line_end < self.line_start:
            raise ValueError("line_end is before line_start")
        return self


class ElementBase(FrozenModel):
    element_id: str = Field(min_length=1)
    locator: Locator
    raw: str
    text: str


class PageMarker(ElementBase):
    kind: Literal["page_marker"] = "page_marker"
    page: int


class Heading(ElementBase):
    kind: Literal["heading"] = "heading"
    level: int
    number: Optional[str]
    title: str


class Paragraph(ElementBase):
    kind: Literal["paragraph"] = "paragraph"


class ListItem(ElementBase):
    kind: Literal["list_item"] = "list_item"
    marker: str


class TableCell(FrozenModel):
    row: int
    col: int
    text: str


class Table(ElementBase):
    kind: Literal["table"] = "table"
    table_index: int
    header: tuple[str, ...]
    rows: tuple[tuple[TableCell, ...], ...]

    @model_validator(mode="after")
    def _cells_know_their_position(self) -> Table:
        for r, cells in enumerate(self.rows, start=1):
            for c, cell in enumerate(cells, start=1):
                if (cell.row, cell.col) != (r, c):
                    raise ValueError(f"the cell at row {r}, column {c} is numbered differently")
        return self


class Image(ElementBase):
    kind: Literal["image"] = "image"
    image_id: str
    file_name: str
    title: str


class Unclassified(ElementBase):
    kind: Literal["unclassified"] = "unclassified"


Element = Annotated[
    Union[PageMarker, Heading, Paragraph, ListItem, Table, Image, Unclassified],
    Field(discriminator="kind"),
]


class Document(FrozenModel):
    doc_id: str
    version: str
    variant: Variant
    language: Language
    file_name: str
    sha256: str
    elements: tuple[Element, ...]

    @model_validator(mode="after")
    def _element_ids_are_unique(self) -> Document:
        seen: set[str] = set()
        for element in self.elements:
            if element.element_id in seen:
                raise ValueError(f"element_id {element.element_id} is used twice")
            seen.add(element.element_id)
        return self


def element_id_for(index: int) -> str:
    """1-based position in the document -> 'e0001'."""
    return f"e{index:04d}"


def cell_ref(element_id: str, row: int, col: int) -> str:
    """Reference to one table cell, e.g. 'e0017:r2c3'. The header row is row 0."""
    return f"{element_id}:r{row}c{col}"
