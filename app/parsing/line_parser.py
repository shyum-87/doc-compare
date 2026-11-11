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
    Image,
    ListItem,
    Locator,
    PageMarker,
    Paragraph,
    Table,
    TableCell,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?([0-9]{1,6})\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"([0-9]+(?:\.[0-9]+)*)\.?\s+(\S.*)")
_SEPARATOR_CELL_RE = re.compile(r":?-+:?")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_IMAGE_ANGLE_RE = re.compile(r'!\[([^\]]*)\]\(<([^">]+?)(?:\s+"([^"]*)")?\s*>\)')
_IMAGE_PLAIN_RE = re.compile(r'!\[([^\]]*)\]\(([^\s"<>()]+)(?:\s+"([^"]*)")?\)')
_IMAGE_MARK_RE = re.compile(r"!\[[^\]]*\]\(")
_LIST_PAREN_RE = re.compile(r"(\d+\))(\s*)(\S.*)")
_LIST_DOT_RE = re.compile(r"(\d+\.)(\s+)(\S.*)")
_LIST_BULLET_RE = re.compile(r"([-*])(\s+)(\S.*)")
_NUMBER_DOT_RE = re.compile(r"\d+\.(?:\s|$)")
_RULE_LINE_RE = re.compile(r"(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,}")
_HTML_LINE_RE = re.compile(r"</?[A-Za-z][^>]*>")
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


def _unmarked(text: str) -> str:
    """The text without hiding characters and '*', with its spaces kept."""
    return "".join(char for char in text if not (_hides(char) or char == "*"))


def _starts_hidden(text: str) -> bool:
    """True when a hiding character comes before the first character that shows."""
    for char in text:
        if _hides(char):
            return True
        if not (char == "*" or char.isspace()):
            return False
    return False


def _is_number(char: str) -> bool:
    """True for a character of a number category: a digit of any script, a fraction, ..."""
    return bool(char) and unicodedata.category(char).startswith("N")


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


def _cells_as_written(line: str) -> list[str]:
    """'|a|**b**| ' -> ['a', '**b**']. An escaped pipe (\\|) does not split."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in _CELL_SPLIT_RE.split(body)]


def split_table_row(line: str) -> list[str]:
    """'|a|**b**| ' -> ['a', 'b']. An escaped pipe (\\|) does not split."""
    return [clean_text(cell.replace("\\|", "|")) for cell in _cells_as_written(line)]


def _is_separator_row(line: str) -> bool:
    """True when every cell of the line, as written, is dashes with optional colons."""
    return all(_SEPARATOR_CELL_RE.fullmatch(cell) for cell in _cells_as_written(line))


def _continues_table(line: str) -> bool:
    """True for a pipe line with no character in its middle that other tools end a line at."""
    body = line.strip()
    return body.startswith("|") and len(body.splitlines()) == 1


def _is_table(block: list[str]) -> bool:
    """A header, then a separator row, and no separator row anywhere else.

    A separator row in another place can mean that two tables have run together or that
    a header went missing, so the block is not read as a table: nothing is guessed.
    """
    return [index for index, line in enumerate(block) if _is_separator_row(line)] == [1]


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)
        self.table_count = 0

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
        # an image inside a heading, a table, a list item or a paragraph is not read either
        if element.kind not in ("image", "unclassified"):
            for offset, line in enumerate(element.raw.split("\n")):
                if _IMAGE_MARK_RE.search(line):
                    self.flag("IMAGE_PRESENT", element, element.locator.line_start + offset)

    def flag(self, code: FindingCode, element: Element, line: Optional[int] = None) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=line if line is not None else element.locator.line_start,
                line_end=line if line is not None else element.locator.line_end,
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

    def table(self, block: list[str], line_start: int) -> None:
        self.table_count += 1
        header = split_table_row(block[0])
        rows = [split_table_row(line) for line in block[2:]]
        element = Table(
            element_id=self.next_id(),
            locator=self.locator(line_start, line_start + len(block) - 1),
            raw="\n".join(block),
            text="\n".join(" | ".join(cells) for cells in [header, *rows]),
            table_index=self.table_count,
            header=tuple(header),
            rows=tuple(
                tuple(TableCell(row=r, col=c, text=text) for c, text in enumerate(cells, start=1))
                for r, cells in enumerate(rows, start=1)
            ),
        )
        self.add(element)
        if len(split_table_row(block[1])) != len(header):
            self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + 1)
        for offset, cells in enumerate(rows, start=2):
            if len(cells) != len(header):
                self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + offset)

    def image(self, match: re.Match[str], line_no: int, raw: str) -> None:
        title = match.group(3) or ""
        element = Image(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=title,
            image_id=match.group(1),
            file_name=match.group(2).strip(),
            title=title,
        )
        self.add(element)
        self.flag("IMAGE_PRESENT", element)

    def list_item(self, marker: str, body: str, line_no: int, raw: str) -> None:
        self.add(
            ListItem(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(body),
                marker=marker,
            )
        )

    def paragraph(self, stripped: str, line_no: int, raw: str) -> Paragraph:
        element = Paragraph(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(stripped),
        )
        self.add(element)
        return element

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

        # 4. table: consecutive pipe lines whose second line is the only separator row.
        # A pipe line that holds a character other tools end a line at ends the block
        # and is left to the check above
        if stripped.startswith("|"):
            block = [raw]
            while index < len(lines) and _continues_table(lines[index]):
                block.append(lines[index])
                index += 1
            if _is_table(block):
                builder.table(block, line_no)
            else:
                for offset, block_line in enumerate(block):
                    builder.unclassified(block_line.strip(), line_no + offset, block_line)
            continue

        # 5. image
        if stripped.startswith("!["):
            match = _IMAGE_ANGLE_RE.fullmatch(stripped) or _IMAGE_PLAIN_RE.fullmatch(stripped)
            if match and match.group(1).strip() and match.group(2).strip():
                builder.image(match, line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 8 (checked early). lines that look structural but are not interpreted
        if (
            stripped.startswith(("```", "~~~", ">", "<!--"))
            or _RULE_LINE_RE.fullmatch(stripped)
            or _HTML_LINE_RE.match(stripped)
        ):
            builder.unclassified(stripped, line_no, raw)
            continue

        # 6. list item
        match = (
            _LIST_PAREN_RE.fullmatch(stripped)
            or _LIST_DOT_RE.fullmatch(stripped)
            or _LIST_BULLET_RE.fullmatch(stripped)
        )
        if match:
            marker, gap, body = match.groups()
            dotted = marker.endswith(".") and _NUMBER_DOT_RE.match(_unmarked(body))
            if _starts_hidden(gap + body) or dotted:
                # a hiding character next to the marker, or '2024. 5. 1 ...': not decided here
                builder.unclassified(stripped, line_no, raw)
            else:
                builder.list_item(marker, body, line_no, raw)
            continue
        if stripped.startswith("-"):
            rest = stripped[1:]
            shown = _unmarked(rest).lstrip()
            if not shown or shown.startswith("-") or _starts_hidden(rest):
                builder.unclassified(stripped, line_no, raw)
            elif _is_number(shown[0]) or (shown[0] in ".," and _is_number(shown[1:2])):
                # '-18℃ ...', '-**18℃**', '-.5': list item or negative number? Not decided here.
                element = builder.paragraph(stripped, line_no, raw)
                builder.flag("AMBIGUOUS_LIST_OR_NEGATIVE", element)
            else:
                builder.list_item("-", rest, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)
