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
# characters that show nothing of their own: control and format characters, code points
# with no character assigned, combining marks, and letters that are drawn blank
_HIDING_CATEGORIES = ("Cc", "Cf", "Cn", "Mn", "Me")
_BLANK_LETTERS = frozenset(
    "\N{HANGUL CHOSEONG FILLER}\N{HANGUL JUNGSEONG FILLER}\N{HANGUL FILLER}"
    "\N{HALFWIDTH HANGUL FILLER}\N{BRAILLE PATTERN BLANK}"
)


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BR_RE.sub("\n", _BOLD_RE.sub(r"\1", value))


def _hides(char: str) -> bool:
    """True for a character that shows nothing of its own and so can hide a marker."""
    if char == "\t":
        return False
    return unicodedata.category(char) in _HIDING_CATEGORIES or char in _BLANK_LETTERS


def _squeezed(line: str) -> str:
    """The line without what a reader does not see: hiding characters, '*' and spaces."""
    return "".join(char for char in line if not (_hides(char) or char == "*" or char.isspace()))


def _split_heading(rest: str) -> tuple[Optional[str], str]:
    """'3.1 **A**<br>B' -> ('3.1', 'A\nB'). The number is read with the bold marks stripped."""
    plain = _BOLD_RE.sub(r"\1", rest)
    match = _HEADING_NUMBER_RE.fullmatch(plain)
    if match:
        return match.group(1), _BR_RE.sub("\n", match.group(2))
    return None, _BR_RE.sub("\n", plain)


def _reads_plainly(rest: str) -> bool:
    """False when a hiding character opens the heading or keeps its number from being read.

    The number read from the heading must be the number that is left once the hiding
    characters and every '*' are taken out.
    """
    shown = "".join(char for char in rest if not (_hides(char) or char == "*")).strip()
    opening = rest.lstrip("* \t")[:1]
    if any(map(_hides, opening)):
        return False
    return _split_heading(rest)[0] == _split_heading(shown)[0]


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label, _ in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)
        if not self.seen_page_marker:
            self.before_first_page.append(element)

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
        previous = self.page
        if not self.seen_page_marker and self.before_first_page:
            self.findings.append(
                new_finding(
                    "CONTENT_BEFORE_FIRST_PAGE",
                    self.variant,
                    element_ids=tuple(e.element_id for e in self.before_first_page),
                    line_start=self.before_first_page[0].locator.line_start,
                    line_end=self.before_first_page[-1].locator.line_end,
                )
            )
        self.seen_page_marker = True
        self.page = number
        element = PageMarker(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=raw.strip(),
            page=number,
        )
        self.add(element)
        if previous is not None and number <= previous:
            self.flag("PAGE_NUMBER_NOT_INCREASING", element)

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        number, title = _split_heading(rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        parent_number = self.headings[-1][2] if self.headings else None
        mismatch = (
            number is not None
            and parent_number is not None
            and not number.startswith(parent_number + ".")
        )
        self.headings.append((level, number if number is not None else title, number))
        element = Heading(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(rest),
            level=level,
            number=number,
            title=title,
        )
        self.add(element)
        if mismatch:
            self.flag("HEADING_NUMBER_MISMATCH", element)

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

        # a line that starts with a hiding character, or that holds a character other
        # tools end a line at, is not interpreted: a marker could be hidden in it
        if _hides(stripped[0]) or len(stripped.splitlines()) > 1:
            builder.unclassified(stripped, line_no, raw)
            continue

        # 2. page marker. '[PAGE' is reserved: a line that holds it, however it is
        # wrapped or broken up, is a marker and nothing else, or it is not interpreted
        if "[PAGE" in _squeezed(stripped).upper():
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match and _reads_plainly(match.group(2)):
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)
