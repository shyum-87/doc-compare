"""Findings and the ingest result."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.findings import (
    DOCUMENT_SCOPE_CODES,
    INFO_CODES,
    Failure,
    FindingCode,
    IngestResult,
    new_finding,
)

ALL_CODES = get_args(FindingCode)


def test_there_are_fourteen_finding_codes():
    assert len(ALL_CODES) == 14
    assert INFO_CODES <= set(ALL_CODES)
    assert DOCUMENT_SCOPE_CODES <= set(ALL_CODES)


@pytest.mark.parametrize("code", ALL_CODES)
def test_the_grade_is_fixed_by_the_code(code):
    expected = "info" if code in {"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"} else "review_required"
    assert new_finding(code, "translated").grade == expected


def test_a_finding_points_at_elements_and_lines():
    finding = new_finding(
        "TOKEN_MISMATCH",
        "translated",
        element_ids=("e0017",),
        counterpart_element_ids=("e0017",),
        cell_ref="e0017:r2c3",
        line_start=39,
        line_end=39,
        missing_tokens=("num:1,0",),
        extra_tokens=("num:2.0",),
    )
    assert finding.document == "translated"
    assert finding.cell_ref == "e0017:r2c3"
    assert (finding.line_start, finding.line_end) == (39, 39)


def test_an_unknown_code_is_rejected():
    with pytest.raises(ValidationError):
        new_finding("SOMETHING_ELSE", "translated")


def test_a_failure_names_the_file_unless_the_error_is_internal():
    assert Failure(reason="NOT_UTF8", document="source").document == "source"
    assert Failure(reason="INTERNAL_ERROR").document is None


def test_a_failed_result_carries_no_documents():
    result = IngestResult(
        status="FAILED", parser_version="0.1.0", failure=Failure(reason="EMPTY_DOCUMENT")
    )
    assert result.documents == ()
    assert result.findings == ()
    assert result.translation_check is None
    assert IngestResult.model_validate_json(result.model_dump_json()) == result
