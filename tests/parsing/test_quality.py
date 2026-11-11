"""From findings to a status, and to the elements a finding blocks (D-013)."""

from __future__ import annotations

import pytest

from app.models.findings import new_finding
from app.parsing.quality import blocked_element_ids, decide_status

LINES = ["[PAGE 1]", "## 1 개요", "", "문단 1.", "", "문단 2."]  # e0001 .. e0004


@pytest.fixture
def translated(make_document):
    return make_document(LINES, "translated", "ko")


@pytest.fixture
def source(make_document):
    return make_document(LINES, "source", "en")


def test_no_findings_is_ok():
    assert decide_status([]) == "OK"


def test_info_findings_alone_are_ok():
    findings = [
        new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",)),
        new_finding("HEADING_NUMBER_MISMATCH", "source", element_ids=("e0002",)),
    ]
    assert decide_status(findings) == "OK"


@pytest.mark.parametrize(
    "code",
    [
        "UNCLASSIFIED_LINE",
        "AMBIGUOUS_LIST_OR_NEGATIVE",
        "TABLE_ROW_WIDTH_MISMATCH",
        "NO_PAGE_MARKER",
        "CONTENT_BEFORE_FIRST_PAGE",
        "PAGE_NUMBER_NOT_INCREASING",
        "SOURCE_NOT_PROVIDED",
        "SKELETON_MISMATCH",
        "SEGMENT_UNALIGNED",
        "TABLE_SHAPE_MISMATCH",
        "TOKEN_MISMATCH",
        "NUMBER_FORMAT_AMBIGUOUS",
    ],
)
def test_one_review_finding_is_enough(code):
    findings = [
        new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",)),
        new_finding(code, "source"),
    ]
    assert decide_status(findings) == "REVIEW_REQUIRED"


def test_the_status_is_never_decided_by_a_ratio():
    """One finding among many clean elements still asks for review."""
    findings = [new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",))] * 500
    findings.append(new_finding("TOKEN_MISMATCH", "translated", element_ids=("e0004",)))
    assert decide_status(findings) == "REVIEW_REQUIRED"


def test_nothing_is_blocked_without_findings(translated):
    assert blocked_element_ids(translated, []) == frozenset()


def test_a_finding_blocks_its_elements_on_both_sides(translated, source):
    finding = new_finding(
        "TOKEN_MISMATCH",
        "translated",
        element_ids=("e0003",),
        counterpart_element_ids=("e0004",),
    )
    assert blocked_element_ids(translated, [finding]) == {"e0003"}
    assert blocked_element_ids(source, [finding]) == {"e0004"}


def test_a_segment_finding_blocks_every_element_of_the_segment(translated, source):
    finding = new_finding(
        "SEGMENT_UNALIGNED",
        "translated",
        element_ids=("e0003", "e0004"),
        counterpart_element_ids=("e0002", "e0003", "e0004"),
    )
    assert blocked_element_ids(translated, [finding]) == {"e0003", "e0004"}
    assert blocked_element_ids(source, [finding]) == {"e0002", "e0003", "e0004"}


def test_a_finding_raised_on_the_source_side(translated, source):
    finding = new_finding(
        "NUMBER_FORMAT_AMBIGUOUS",
        "source",
        element_ids=("e0004",),
        counterpart_element_ids=("e0003",),
    )
    assert blocked_element_ids(source, [finding]) == {"e0004"}
    assert blocked_element_ids(translated, [finding]) == {"e0003"}


def test_info_findings_block_nothing(translated, source):
    findings = [
        new_finding("IMAGE_PRESENT", "translated", element_ids=("e0003",)),
        new_finding("HEADING_NUMBER_MISMATCH", "source", element_ids=("e0002",)),
    ]
    assert blocked_element_ids(translated, findings) == frozenset()
    assert blocked_element_ids(source, findings) == frozenset()


@pytest.mark.parametrize("code", ["NO_PAGE_MARKER", "SOURCE_NOT_PROVIDED"])
def test_a_document_scope_finding_blocks_the_whole_document(translated, source, code):
    finding = new_finding(code, "translated")
    assert blocked_element_ids(translated, [finding]) == {"e0001", "e0002", "e0003", "e0004"}
    assert blocked_element_ids(source, [finding]) == frozenset()


def test_findings_add_up(translated):
    findings = [
        new_finding("UNCLASSIFIED_LINE", "translated", element_ids=("e0003",)),
        new_finding("TOKEN_MISMATCH", "translated", element_ids=("e0004",)),
        new_finding("IMAGE_PRESENT", "translated", element_ids=("e0002",)),
    ]
    assert blocked_element_ids(translated, findings) == {"e0003", "e0004"}
