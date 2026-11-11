"""Reference values of the sample documents (spec section 2)."""

from __future__ import annotations

from collections import Counter

import pytest

from app.parsing.line_parser import parse_lines
from app.parsing.reader import read_lines

EXPECTED_KINDS = {
    "page_marker": 4,
    "heading": 6,
    "table": 5,
    "image": 3,
    "list_item": 14,
    "paragraph": 17,
}


def _parse(path):
    return parse_lines(read_lines(path).lines, "source")


def test_the_korean_sample_has_49_elements(ko_sample):
    elements, _ = _parse(ko_sample)
    assert len(elements) == 49
    assert Counter(element.kind for element in elements) == EXPECTED_KINDS  # no 'unclassified'
    assert [element.element_id for element in elements] == [f"e{n:04d}" for n in range(1, 50)]


def test_the_only_findings_are_the_three_images(ko_sample):
    _, findings = _parse(ko_sample)
    assert [finding.code for finding in findings] == ["IMAGE_PRESENT"] * 3
    assert {finding.grade for finding in findings} == {"info"}
    assert [finding.element_ids for finding in findings] == [("e0008",), ("e0021",), ("e0033",)]


def test_the_pages_are_8_to_11(ko_sample):
    elements, _ = _parse(ko_sample)
    markers = [element for element in elements if element.kind == "page_marker"]
    assert [marker.page for marker in markers] == [8, 9, 10, 11]
    assert [marker.element_id for marker in markers] == ["e0001", "e0014", "e0023", "e0036"]


def test_every_element_has_a_page_a_section_and_lines(ko_sample):
    elements, _ = _parse(ko_sample)
    for element in elements:
        assert element.locator.page is not None
        assert 1 <= element.locator.line_start <= element.locator.line_end <= 114
    # only the first page marker stands before the first heading
    assert [element.element_id for element in elements if not element.locator.section_path] == [
        "e0001"
    ]


def test_the_headings(ko_sample):
    elements, _ = _parse(ko_sample)
    headings = [element for element in elements if element.kind == "heading"]
    assert [(heading.level, heading.number) for heading in headings] == [
        (2, "3"),
        (3, "3.1"),
        (3, "3.2"),
        (3, "3.3"),
        (3, "3.4"),
        (3, "3.5"),
    ]
    assert [heading.locator.line_start for heading in headings] == [3, 5, 32, 56, 90, 105]


def test_the_weighing_table_is_e0017(ko_sample):
    elements, _ = _parse(ko_sample)
    table = elements[16]
    assert table.element_id == "e0017"
    assert table.kind == "table"
    assert table.table_index == 2
    assert table.locator.page == 9
    assert table.locator.section_path == ("3", "3.2")
    assert (table.locator.line_start, table.locator.line_end) == (36, 42)
    assert table.header == ("확인 항목", "확인 방법", "판정기준")
    assert len(table.rows) == 5
    assert table.rows[1][2].text == "배합표 대비 ±1.0% 이내"  # e0017:r2c3, line 39


def test_typos_in_the_sample_are_kept(ko_sample):
    elements, _ = _parse(ko_sample)
    text = "\n".join(element.text for element in elements)
    assert "합께" in text
    assert "패덜" in text


def test_the_minus_sign_in_a_table_cell_raises_no_finding(ko_sample):
    elements, findings = _parse(ko_sample)
    table = elements[41]
    assert table.element_id == "e0042"
    assert table.rows[3][1].text == "-18℃이하"  # e0042:r4c2, line 103
    assert "AMBIGUOUS_LIST_OR_NEGATIVE" not in {finding.code for finding in findings}


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_each_source_sample_has_the_same_shape(ko_sample, source_samples, language):
    korean, _ = _parse(ko_sample)
    elements, findings = _parse(source_samples[language])
    assert Counter(element.kind for element in elements) == EXPECTED_KINDS

    def shape(parsed):
        return [
            (e.kind, e.locator.page, e.locator.section_path, e.locator.line_start) for e in parsed
        ]

    assert shape(elements) == shape(korean)
    assert [finding.code for finding in findings] == ["IMAGE_PRESENT"] * 3
