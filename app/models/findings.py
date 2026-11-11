"""Findings, translation-check results and the overall ingest result.

These objects point at documents by element_id; they are never stored inside a Document.
"""

from __future__ import annotations

from typing import Literal, Optional

from app.models.document import Document, FrozenModel, Variant

Status = Literal["FAILED", "REVIEW_REQUIRED", "OK"]
Grade = Literal["review_required", "info"]
FindingCode = Literal[
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
    "HEADING_NUMBER_MISMATCH",
    "IMAGE_PRESENT",
]
FailureReason = Literal["FILE_UNREADABLE", "NOT_UTF8", "EMPTY_DOCUMENT", "INTERNAL_ERROR"]

INFO_CODES: frozenset[str] = frozenset({"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"})
DOCUMENT_SCOPE_CODES: frozenset[str] = frozenset({"NO_PAGE_MARKER", "SOURCE_NOT_PROVIDED"})


class Finding(FrozenModel):
    code: FindingCode
    grade: Grade
    document: Variant
    element_ids: tuple[str, ...] = ()
    counterpart_element_ids: tuple[str, ...] = ()
    cell_ref: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    missing_tokens: tuple[str, ...] = ()
    extra_tokens: tuple[str, ...] = ()


def new_finding(
    code: FindingCode,
    document: Variant,
    *,
    element_ids: tuple[str, ...] = (),
    counterpart_element_ids: tuple[str, ...] = (),
    cell_ref: Optional[str] = None,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    missing_tokens: tuple[str, ...] = (),
    extra_tokens: tuple[str, ...] = (),
) -> Finding:
    """Build a finding; the grade is fixed by the code (D-013)."""
    grade: Grade = "info" if code in INFO_CODES else "review_required"
    return Finding(
        code=code,
        grade=grade,
        document=document,
        element_ids=element_ids,
        counterpart_element_ids=counterpart_element_ids,
        cell_ref=cell_ref,
        line_start=line_start,
        line_end=line_end,
        missing_tokens=missing_tokens,
        extra_tokens=extra_tokens,
    )


class PairResult(FrozenModel):
    translated_ref: str
    source_ref: str
    status: Literal["match", "token_mismatch"]
    missing_tokens: tuple[str, ...] = ()
    extra_tokens: tuple[str, ...] = ()


class UnpairedSegment(FrozenModel):
    reason: Literal["SKELETON_MISMATCH", "SEGMENT_UNALIGNED", "TABLE_SHAPE_MISMATCH"]
    translated_element_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...]


class TranslationCheck(FrozenModel):
    pairs: tuple[PairResult, ...]
    unpaired: tuple[UnpairedSegment, ...]


class Failure(FrozenModel):
    reason: FailureReason
    document: Optional[Variant] = None  # which file; None for an internal error


class IngestResult(FrozenModel):
    status: Status
    parser_version: str
    failure: Optional[Failure] = None
    documents: tuple[Document, ...] = ()
    findings: tuple[Finding, ...] = ()
    translation_check: Optional[TranslationCheck] = None
