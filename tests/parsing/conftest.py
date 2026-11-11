"""Small builders for parser tests."""

from __future__ import annotations

from typing import Callable, Sequence

import pytest

from app.models.document import Document, Element, Language, Variant
from app.models.findings import Finding
from app.parsing.line_parser import parse_lines

Parsed = tuple[tuple[Element, ...], tuple[Finding, ...]]


@pytest.fixture
def parse() -> Callable[..., Parsed]:
    """parse("line 1\\nline 2") -> (elements, findings)"""

    def _parse(text: str, variant: Variant = "source") -> Parsed:
        return parse_lines(tuple(text.split("\n")), variant)

    return _parse


@pytest.fixture
def make_document() -> Callable[..., Document]:
    """make_document(lines, "translated", "ko") -> Document built by the parser"""

    def _make(lines: Sequence[str], variant: Variant, language: Language) -> Document:
        elements, _ = parse_lines(tuple(lines), variant)
        return Document(
            doc_id="SOP-SAMPLE",
            version="1",
            variant=variant,
            language=language,
            file_name="memory.md",
            sha256="0" * 64,
            elements=elements,
        )

    return _make
