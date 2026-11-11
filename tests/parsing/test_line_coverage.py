"""No line may be lost: every non-blank line belongs to exactly one element."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import LineCoverageError, parse_lines, verify_line_coverage
from app.parsing.reader import read_lines

LINES = (
    "[PAGE 1]",
    "",
    "## 1. 개요",
    "문단이다.",
    "|가|나|",
    "|---|---|",
    "|1|2|",
    "",
    "> 해석하지 않는 줄",
    "- 항목",
)


def test_parsed_lines_are_covered():
    elements, _ = parse_lines(LINES, "source")
    verify_line_coverage(LINES, elements)  # does not raise


def test_a_lost_element_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="line 4 is owned by 0 elements"):
        verify_line_coverage(LINES, elements[:2] + elements[3:])


def test_a_line_owned_twice_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="line 4 is owned by 2 elements"):
        verify_line_coverage(LINES, elements + (elements[2],))


def test_an_element_on_a_blank_line_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    paragraph = elements[2]
    moved = paragraph.model_copy(
        update={"locator": paragraph.locator.model_copy(update={"line_start": 2, "line_end": 2})}
    )
    with pytest.raises(LineCoverageError, match="line 2 is owned by 1 elements"):
        verify_line_coverage(LINES, elements[:2] + (moved,) + elements[3:])


def test_an_element_outside_the_file_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="e0006 points outside the file"):
        verify_line_coverage(LINES[:-1], elements)


def test_the_message_holds_no_document_text():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError) as caught:
        verify_line_coverage(LINES, elements[:2] + elements[3:])
    assert "문단" not in str(caught.value)


def test_every_sample_is_covered(ko_sample, source_samples):
    for path in [ko_sample, *source_samples.values()]:
        lines = read_lines(path).lines
        elements, _ = parse_lines(lines, "source")
        verify_line_coverage(lines, elements)
        owned = {
            line_no
            for element in elements
            for line_no in range(element.locator.line_start, element.locator.line_end + 1)
        }
        not_blank = {line_no for line_no, line in enumerate(lines, start=1) if line.strip()}
        assert owned == not_blank
