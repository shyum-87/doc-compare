"""Findings, translation-check results and the overall ingest result.

These objects point at documents by element_id; they are never stored inside a Document.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from app.models.document import Document, FrozenModel, Language, Variant

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


def grade_of(code: str) -> Grade:
    """The grade is fixed by the code (D-013)."""
    return "info" if code in INFO_CODES else "review_required"


class Finding(FrozenModel):
    code: FindingCode
    grade: Grade
    document: Variant
    element_ids: tuple[str, ...] = ()
    counterpart_element_ids: tuple[str, ...] = ()
    cell_ref: Optional[str] = None
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    missing_tokens: tuple[str, ...] = ()
    extra_tokens: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _grade_and_lines_are_consistent(self) -> Finding:
        if self.grade != grade_of(self.code):
            raise ValueError(f"{self.code} cannot have the grade {self.grade}")
        if (self.line_start is None) != (self.line_end is None):
            raise ValueError("line_start and line_end are given together or not at all")
        if self.line_start is not None and self.line_end < self.line_start:
            raise ValueError("line_end is before line_start")
        return self


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
    """Build a finding with the grade its code fixes."""
    return Finding(
        code=code,
        grade=grade_of(code),
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

    @model_validator(mode="after")
    def _status_agrees_with_the_tokens(self) -> PairResult:
        differs = bool(self.missing_tokens or self.extra_tokens)
        if differs != (self.status == "token_mismatch"):
            raise ValueError(f"the status {self.status} disagrees with the token lists")
        return self


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
    # What the caller declared. Without a source file no document carries it, and a
    # FAILED result has no document at all.
    original_language: Language
    failure: Optional[Failure] = None
    documents: tuple[Document, ...] = ()
    findings: tuple[Finding, ...] = ()
    translation_check: Optional[TranslationCheck] = None

    @model_validator(mode="after")
    def _status_agrees_with_the_content(self) -> IngestResult:
        if self.status == "FAILED":
            if self.failure is None:
                raise ValueError("a FAILED result needs a failure")
            if self.documents or self.findings or self.translation_check is not None:
                raise ValueError("a FAILED result carries no documents, findings or check")
            return self
        if self.failure is not None:
            raise ValueError(f"a failure cannot have the status {self.status}")
        if not self.documents:
            raise ValueError(f"the status {self.status} needs a document")
        for document in self.documents:
            if document.variant == "source" and document.language != self.original_language:
                raise ValueError("the source document is not in the original language")
        needs_review = any(finding.grade == "review_required" for finding in self.findings)
        if needs_review != (self.status == "REVIEW_REQUIRED"):
            raise ValueError(f"the status {self.status} disagrees with the findings")
        return self
