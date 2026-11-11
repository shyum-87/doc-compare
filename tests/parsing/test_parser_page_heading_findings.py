"""Findings the parser raises about page markers and heading numbers."""

from __future__ import annotations


def _codes(findings):
    return [finding.code for finding in findings]


def test_content_before_the_first_page_marker(parse):
    elements, findings = parse("## 1. 개요\n쪽 표시보다 앞에 있다.\n[PAGE 1]\n쪽 표시 뒤에 있다.")
    assert [element.locator.page for element in elements] == [None, None, 1, 1]
    assert _codes(findings) == ["CONTENT_BEFORE_FIRST_PAGE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0001", "e0002")
    assert (findings[0].line_start, findings[0].line_end) == (1, 2)


def test_a_document_that_starts_with_a_page_marker_has_no_such_finding(parse):
    _, findings = parse("\n\n[PAGE 1]\n문단이다.")
    assert findings == ()


def test_a_document_without_any_page_marker(parse):
    elements, findings = parse("## 1. 개요\n문단이다.")
    assert [element.locator.page for element in elements] == [None, None]
    assert _codes(findings) == ["NO_PAGE_MARKER"]  # and no CONTENT_BEFORE_FIRST_PAGE
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ()  # it is about the whole document


def test_page_numbers_must_increase(parse):
    elements, findings = parse("[PAGE 8]\n가.\n[PAGE 8]\n나.\n[PAGE 7]\n다.\n[PAGE 9]\n라.")
    assert _codes(findings) == ["PAGE_NUMBER_NOT_INCREASING", "PAGE_NUMBER_NOT_INCREASING"]
    assert [finding.element_ids for finding in findings] == [("e0003",), ("e0005",)]
    assert [finding.line_start for finding in findings] == [3, 5]
    # the marker is still applied as written; nothing is corrected
    assert [element.locator.page for element in elements] == [8, 8, 8, 8, 7, 7, 9, 9]


def test_a_skipped_page_number_is_fine(parse):
    _, findings = parse("[PAGE 8]\n가.\n[PAGE 11]\n나.")
    assert findings == ()


def test_a_heading_number_that_does_not_continue_its_parent(parse):
    _, findings = parse("[PAGE 1]\n## 3. 제조\n### 4.1 조회\n### 3.2 계량")
    assert _codes(findings) == ["HEADING_NUMBER_MISMATCH"]
    assert findings[0].grade == "info"
    assert findings[0].element_ids == ("e0003",)
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_heading_numbers_that_need_no_remark(parse):
    text = "\n".join(
        [
            "[PAGE 1]",
            "## 3. 제조",
            "### 3.1 조회",
            "#### 3.1.1 조건",
            "## 4. 기록",  # a sibling, not a child of 3
            "### 보관",  # no number
            "#### 4.1 기간",  # the parent has no number to compare with
            "## 31. 부록",
            "### 31.1 양식",
        ]
    )
    _, findings = parse(text)
    assert findings == ()


def test_a_number_that_only_starts_with_the_same_digits_is_a_mismatch(parse):
    _, findings = parse("[PAGE 1]\n## 3. 제조\n### 31.1 조회")
    assert _codes(findings) == ["HEADING_NUMBER_MISMATCH"]


def test_findings_name_the_document_they_are_about(parse):
    _, findings = parse("문단이다.", variant="translated")
    assert [finding.document for finding in findings] == ["translated"]


def test_every_finding_names_the_document_it_is_about(parse):
    text = "문단이다.\n[PAGE 2]\n## 3. 제조\n### 4.1 조회\n[PAGE x]\n[PAGE 1]"
    for variant in ("source", "translated"):
        _, findings = parse(text, variant=variant)
        assert _codes(findings) == [
            "CONTENT_BEFORE_FIRST_PAGE",
            "HEADING_NUMBER_MISMATCH",
            "UNCLASSIFIED_LINE",
            "PAGE_NUMBER_NOT_INCREASING",
        ]
        assert {finding.document for finding in findings} == {variant}


def test_a_mismatched_heading_still_opens_its_section(parse):
    elements, findings = parse("[PAGE 1]\n## 3. 제조\n### 4.1 조회\n문단이다.")
    assert _codes(findings) == ["HEADING_NUMBER_MISMATCH"]
    assert elements[2].number == "4.1"  # kept as written: nothing is corrected
    assert elements[2].locator.section_path == ("3", "4.1")
    assert elements[3].locator.section_path == ("3", "4.1")


def test_a_heading_under_a_parent_without_a_number_is_not_compared(parse):
    _, findings = parse("[PAGE 1]\n## 3. 제조\n### 보관\n#### 9.1 기간")
    assert findings == ()


def test_a_page_number_is_compared_with_the_marker_before_it_only(parse):
    _, findings = parse("[PAGE 3]\n가.\n[PAGE 1]\n나.\n[PAGE 2]\n다.")
    assert _codes(findings) == ["PAGE_NUMBER_NOT_INCREASING"]
    assert findings[0].element_ids == ("e0003",)
