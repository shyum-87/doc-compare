"""Whole flow: files -> documents -> findings -> status. Fails closed.

Expected input problems come back as a status, never as an exception. Anything
unexpected is caught at the outermost level and turned into FAILED, so a partly
processed document is never returned as if it were a normal result.

Logs carry codes, element IDs, line numbers and counts only: no document text.
"""

from __future__ import annotations

import logging
import traceback
from collections import Counter
from pathlib import Path
from typing import Optional, Union, get_args

from app.models.document import Document, Language, Variant
from app.models.findings import Failure, Finding, IngestResult, new_finding
from app.parsing.line_parser import parse_lines, verify_line_coverage
from app.parsing.quality import decide_status
from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation

# Raise this whenever a parsing rule or a token rule changes.
PARSER_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


def _load(
    path: Path, *, doc_id: str, version: str, variant: Variant, language: Language
) -> Union[Failure, tuple[Document, tuple[Finding, ...]]]:
    read = read_lines(path)
    if read.error is not None or read.sha256 is None:
        logger.error("cannot read the %s file: %s", variant, read.error)
        return Failure(reason=read.error or "FILE_UNREADABLE", document=variant)
    elements, findings = parse_lines(read.lines, variant)
    verify_line_coverage(read.lines, elements)
    document = Document(
        doc_id=doc_id,
        version=version,
        variant=variant,
        language=language,
        file_name=read.file_name,
        sha256=read.sha256,
        elements=elements,
    )
    logger.info("read the %s file: %d lines, %d elements", variant, len(read.lines), len(elements))
    return document, findings


def _failed(failure: Failure, original_language: Language) -> IngestResult:
    return IngestResult(
        status="FAILED",
        parser_version=PARSER_VERSION,
        original_language=original_language,
        failure=failure,
    )


def _ingest(
    main_path: Path,
    *,
    doc_id: str,
    version: str,
    original_language: Language,
    source_path: Optional[Path],
) -> IngestResult:
    # A Korean baseline document was never translated, so it is its own source.
    main_variant: Variant = "source" if original_language == "ko" else "translated"
    main = _load(main_path, doc_id=doc_id, version=version, variant=main_variant, language="ko")
    if isinstance(main, Failure):
        return _failed(main, original_language)
    documents = [main[0]]
    findings = list(main[1])
    translation_check = None

    if original_language != "ko":
        if source_path is None:
            findings.append(new_finding("SOURCE_NOT_PROVIDED", "translated"))
        else:
            source = _load(
                source_path,
                doc_id=doc_id,
                version=version,
                variant="source",
                language=original_language,
            )
            if isinstance(source, Failure):
                return _failed(source, original_language)
            documents.append(source[0])
            findings.extend(source[1])
            translation_check, check_findings = check_translation(main[0], source[0])
            findings.extend(check_findings)

    status = decide_status(findings)
    counts = Counter(finding.code for finding in findings)
    logger.info("status: %s", status)
    logger.info(
        "findings: %s",
        ", ".join(f"{code}={count}" for code, count in sorted(counts.items())) or "none",
    )
    return IngestResult(
        status=status,
        parser_version=PARSER_VERSION,
        original_language=original_language,
        documents=tuple(documents),
        findings=tuple(findings),
        translation_check=translation_check,
    )


def ingest(
    main_path: Path,
    *,
    doc_id: str,
    version: str,
    original_language: Language,
    source_path: Optional[Path] = None,
) -> IngestResult:
    """Read one document (and its source, for a translated one) and check it."""
    # Mistakes of the caller are refused before anything is read. Every result names the
    # original language, so a result cannot be built around a language that is not one.
    if original_language not in get_args(Language):
        raise ValueError("the original language is not one of " + ", ".join(get_args(Language)))
    if original_language == "ko" and source_path is not None:
        raise ValueError("a Korean baseline document takes no source file")
    try:
        return _ingest(
            main_path,
            doc_id=doc_id,
            version=version,
            original_language=original_language,
            source_path=source_path,
        )
    except Exception as error:  # fail closed: nothing may escape as a result
        frames = traceback.extract_tb(error.__traceback__)
        where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "unknown"
        # The message of the exception may quote document text, so only its type is logged.
        logger.error("internal error: %s at %s", type(error).__name__, where)
        return _failed(Failure(reason="INTERNAL_ERROR"), original_language)
