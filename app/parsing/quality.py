"""Findings -> result status, and which elements a finding blocks (D-013).

A document is never passed or failed by a ratio. Findings block the elements they point at.
"""

from __future__ import annotations

from typing import Iterable

from app.models.document import Document
from app.models.findings import DOCUMENT_SCOPE_CODES, Finding, Status


def decide_status(findings: Iterable[Finding]) -> Status:
    """REVIEW_REQUIRED if any finding has the grade 'review_required', otherwise OK."""
    if any(finding.grade == "review_required" for finding in findings):
        return "REVIEW_REQUIRED"
    return "OK"


def blocked_element_ids(document: Document, findings: Iterable[Finding]) -> frozenset[str]:
    """IDs of the elements of `document` that a later verdict may not rely on for a PASS.

    A document-scope finding blocks every element of its document. Other findings block
    `element_ids` in their own document and `counterpart_element_ids` in the other one.
    Findings with the grade 'info' block nothing.
    """
    blocked: set[str] = set()
    for finding in findings:
        if finding.grade != "review_required":
            continue
        if finding.document == document.variant:
            if finding.code in DOCUMENT_SCOPE_CODES:
                return frozenset(element.element_id for element in document.elements)
            blocked.update(finding.element_ids)
        else:
            blocked.update(finding.counterpart_element_ids)
    return frozenset(blocked)
