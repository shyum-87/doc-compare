"""Findings and the ingest result."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.document import Document, Locator, Paragraph
from app.models.findings import (
    DOCUMENT_SCOPE_CODES,
    INFO_CODES,
    Failure,
    Finding,
    FindingCode,
    IngestResult,
    PairResult,
    new_finding,
)

ALL_CODES = get_args(FindingCode)


def _document() -> Document:
    paragraph = Paragraph(
        element_id="e0001",
        locator=Locator(page=1, section_path=(), line_start=1, line_end=1),
        raw="계량한다.",
        text="계량한다.",
    )
    return Document(
        doc_id="SOP-SAMPLE",
        version="1",
        variant="source",
        language="ko",
        file_name="sample.md",
        sha256="0" * 64,
        elements=(paragraph,),
    )


def _result(status: str, **fields: object) -> IngestResult:
    fields.setdefault("original_language", "ko")
    return IngestResult(status=status, parser_version="0.1.0", **fields)


def test_there_are_fourteen_finding_codes():
    assert len(ALL_CODES) == 14
    assert INFO_CODES == {"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"}
    assert DOCUMENT_SCOPE_CODES == {"NO_PAGE_MARKER", "SOURCE_NOT_PROVIDED"}
    assert INFO_CODES | DOCUMENT_SCOPE_CODES <= set(ALL_CODES)


@pytest.mark.parametrize("code", ALL_CODES)
def test_the_grade_is_fixed_by_the_code(code):
    expected = "info" if code in {"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"} else "review_required"
    assert new_finding(code, "translated").grade == expected


@pytest.mark.parametrize("code", ALL_CODES)
def test_a_finding_cannot_carry_another_grade(code):
    wrong = "review_required" if code in {"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"} else "info"
    with pytest.raises(ValidationError):
        Finding(code=code, grade=wrong, document="translated")


def test_a_finding_points_at_elements_and_lines():
    finding = new_finding(
        "TOKEN_MISMATCH",
        "translated",
        element_ids=("e0017",),
        counterpart_element_ids=("e0018",),
        cell_ref="e0017:r2c3",
        line_start=39,
        line_end=39,
        missing_tokens=("num:1,0",),
        extra_tokens=("num:2.0",),
    )
    assert finding.document == "translated"
    assert finding.element_ids == ("e0017",)
    assert finding.counterpart_element_ids == ("e0018",)
    assert finding.cell_ref == "e0017:r2c3"
    assert (finding.line_start, finding.line_end) == (39, 39)
    assert finding.missing_tokens == ("num:1,0",)
    assert finding.extra_tokens == ("num:2.0",)


@pytest.mark.parametrize(("line_start", "line_end"), [(0, 1), (40, 39), (39, None), (None, 39)])
def test_a_finding_rejects_impossible_line_numbers(line_start, line_end):
    with pytest.raises(ValidationError):
        new_finding("TOKEN_MISMATCH", "translated", line_start=line_start, line_end=line_end)


def test_an_unknown_code_is_rejected():
    with pytest.raises(ValidationError):
        new_finding("SOMETHING_ELSE", "translated")


def test_a_pair_is_a_mismatch_exactly_when_tokens_differ():
    with pytest.raises(ValidationError):
        PairResult(
            translated_ref="e0001", source_ref="e0001", status="match", missing_tokens=("num:1",)
        )
    with pytest.raises(ValidationError):
        PairResult(translated_ref="e0001", source_ref="e0001", status="token_mismatch")


def test_a_failure_names_the_file_unless_the_error_is_internal():
    assert Failure(reason="NOT_UTF8", document="source").document == "source"
    assert Failure(reason="INTERNAL_ERROR").document is None


def test_a_failed_result_carries_no_documents():
    result = _result("FAILED", failure=Failure(reason="EMPTY_DOCUMENT"))
    assert result.documents == ()
    assert result.findings == ()
    assert result.translation_check is None
    assert IngestResult.model_validate_json(result.model_dump_json()) == result


def test_a_result_with_documents_survives_a_json_round_trip():
    review = new_finding("UNCLASSIFIED_LINE", "source", element_ids=("e0001",))
    result = _result("REVIEW_REQUIRED", documents=(_document(),), findings=(review,))
    assert IngestResult.model_validate_json(result.model_dump_json()) == result


def test_info_findings_do_not_stop_an_ok_result():
    info = new_finding("IMAGE_PRESENT", "source", element_ids=("e0001",))
    assert _result("OK", documents=(_document(),), findings=(info,)).status == "OK"


@pytest.mark.parametrize(
    ("status", "fields"),
    [
        ("FAILED", {}),
        ("FAILED", {"failure": Failure(reason="NOT_UTF8"), "documents": (_document(),)}),
        (
            "FAILED",
            {
                "failure": Failure(reason="NOT_UTF8"),
                "findings": (new_finding("NO_PAGE_MARKER", "source"),),
            },
        ),
        ("OK", {"documents": (_document(),), "failure": Failure(reason="INTERNAL_ERROR")}),
        ("OK", {}),
        (
            "OK",
            {"documents": (_document(),), "findings": (new_finding("NO_PAGE_MARKER", "source"),)},
        ),
        ("REVIEW_REQUIRED", {"documents": (_document(),)}),
        (
            "REVIEW_REQUIRED",
            {"documents": (_document(),), "findings": (new_finding("IMAGE_PRESENT", "source"),)},
        ),
    ],
)
def test_a_result_cannot_contradict_its_status(status, fields):
    with pytest.raises(ValidationError):
        _result(status, **fields)


def test_a_result_always_names_the_original_language():
    failure = Failure(reason="EMPTY_DOCUMENT")
    assert _result("FAILED", failure=failure, original_language="zh").original_language == "zh"
    with pytest.raises(ValidationError):
        IngestResult(status="FAILED", parser_version="0.1.0", failure=failure)
    with pytest.raises(ValidationError):
        _result("FAILED", failure=failure, original_language="ja")


def test_the_original_language_survives_a_json_round_trip():
    result = _result("FAILED", failure=Failure(reason="EMPTY_DOCUMENT"), original_language="vi")
    assert '"original_language":"vi"' in result.model_dump_json()
    assert IngestResult.model_validate_json(result.model_dump_json()) == result


def test_a_source_document_is_in_the_original_language():
    # _document() is a source document in Korean
    assert _result("OK", documents=(_document(),), original_language="ko").status == "OK"
    with pytest.raises(ValidationError):
        _result("OK", documents=(_document(),), original_language="vi")
