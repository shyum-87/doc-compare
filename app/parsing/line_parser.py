"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Locator,
    PageMarker,
    Paragraph,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?([0-9]{1,6})\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"([0-9]+(?:\.[0-9]+)*)\.?\s+(\S.*)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INVISIBLE = ("Cc", "Cf")  # Unicode categories: control and format characters


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BR_RE.sub("\n", _BOLD_RE.sub(r"\1", value))


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.headings: list[tuple[int, str]] = []  # (level, label)

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)

    def flag(self, code: FindingCode, element: Element) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=element.locator.line_start,
                line_end=element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        self.page = number
        self.add(
            PageMarker(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=raw.strip(),
                page=number,
            )
        )

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(_BOLD_RE.sub(r"\1", rest))
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        self.headings.append((level, number if number is not None else title))
        self.add(
            Heading(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(rest),
                level=level,
                number=number,
                title=title,
            )
        )

    def paragraph(self, stripped: str, line_no: int, raw: str) -> None:
        self.add(
            Paragraph(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(stripped),
            )
        )

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # a line that starts with an invisible character is not interpreted:
        # the character would hide a marker from every rule below
        if unicodedata.category(stripped[0]) in _INVISIBLE:
            builder.unclassified(stripped, line_no, raw)
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    return tuple(builder.elements), tuple(builder.findings)
