"""Check a Korean translation (rag_ko.md) against its source (rag.md).

This is a check inside one target document, not a comparison of baseline and target.
Elements are paired one-to-one (D-008); where that fails the segment stays unpaired
and nothing is guessed about which element is missing.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional, Sequence

from app.models.document import Document, Element, Language, cell_ref
from app.models.findings import (
    Finding,
    FindingCode,
    PairResult,
    TranslationCheck,
    UnpairedSegment,
    new_finding,
)
from app.parsing.tokens import compare_tokens, extract_tokens

_SKELETON_KINDS = ("page_marker", "heading")


def _skeleton_key(element: Element) -> tuple:
    if element.kind == "page_marker":
        return ("page", element.page)
    return ("heading", element.level, element.number or "")


def _ids(elements: Sequence[Element]) -> tuple[str, ...]:
    return tuple(element.element_id for element in elements)


class _Checker:
    def __init__(self, translated_language: Language, source_language: Language) -> None:
        self.translated_language = translated_language
        self.source_language = source_language
        self.pairs: list[PairResult] = []
        self.unpaired: list[UnpairedSegment] = []
        self.findings: list[Finding] = []

    def unpair(
        self,
        code: FindingCode,
        translated: Sequence[Element],
        source: Sequence[Element],
    ) -> None:
        assert code in ("SKELETON_MISMATCH", "SEGMENT_UNALIGNED", "TABLE_SHAPE_MISMATCH")
        self.unpaired.append(
            UnpairedSegment(
                reason=code,
                translated_element_ids=_ids(translated),
                source_element_ids=_ids(source),
            )
        )
        self.findings.append(
            new_finding(
                code,
                "translated",
                element_ids=_ids(translated),
                counterpart_element_ids=_ids(source),
                line_start=translated[0].locator.line_start if translated else None,
                line_end=translated[-1].locator.line_end if translated else None,
            )
        )

    def compare_text(
        self,
        translated: Element,
        source: Element,
        translated_text: str,
        source_text: str,
        *,
        translated_cell: Optional[str] = None,
        source_cell: Optional[str] = None,
        line: Optional[int] = None,
        source_line: Optional[int] = None,
    ) -> None:
        diff = compare_tokens(
            extract_tokens(translated_text, self.translated_language),
            extract_tokens(source_text, self.source_language),
        )
        self.pairs.append(
            PairResult(
                translated_ref=translated_cell or translated.element_id,
                source_ref=source_cell or source.element_id,
                status="match" if diff.is_match else "token_mismatch",
                missing_tokens=diff.missing,
                extra_tokens=diff.extra,
            )
        )
        translated_lines = (
            (line, line)
            if line is not None
            else (translated.locator.line_start, translated.locator.line_end)
        )
        source_lines = (
            (source_line, source_line)
            if source_line is not None
            else (source.locator.line_start, source.locator.line_end)
        )
        if not diff.is_match:
            self.findings.append(
                new_finding(
                    "TOKEN_MISMATCH",
                    "translated",
                    element_ids=(translated.element_id,),
                    counterpart_element_ids=(source.element_id,),
                    cell_ref=translated_cell,
                    line_start=translated_lines[0],
                    line_end=translated_lines[1],
                    missing_tokens=diff.missing,
                    extra_tokens=diff.extra,
                )
            )
        if diff.ambiguous_translated:
            self.findings.append(
                new_finding(
                    "NUMBER_FORMAT_AMBIGUOUS",
                    "translated",
                    element_ids=(translated.element_id,),
                    counterpart_element_ids=(source.element_id,),
                    cell_ref=translated_cell,
                    line_start=translated_lines[0],
                    line_end=translated_lines[1],
                )
            )
        if diff.ambiguous_source:
            self.findings.append(
                new_finding(
                    "NUMBER_FORMAT_AMBIGUOUS",
                    "source",
                    element_ids=(source.element_id,),
                    counterpart_element_ids=(translated.element_id,),
                    cell_ref=source_cell,
                    line_start=source_lines[0],
                    line_end=source_lines[1],
                )
            )

    def pair(self, translated: Element, source: Element) -> None:
        """Both elements have the same kind."""
        if translated.kind == "page_marker":
            self.pairs.append(
                PairResult(
                    translated_ref=translated.element_id,
                    source_ref=source.element_id,
                    status="match",
                )
            )
        elif translated.kind == "heading":
            self.compare_text(translated, source, translated.title, source.title)
        elif translated.kind == "table":
            self.pair_table(translated, source)
        elif translated.kind == "image" and translated.image_id != source.image_id:
            self.unpair("SEGMENT_UNALIGNED", [translated], [source])
        else:
            self.compare_text(translated, source, translated.text, source.text)

    def pair_table(self, translated: Element, source: Element) -> None:
        def shape(table: Element) -> tuple:
            return (len(table.header), tuple(len(row) for row in table.rows))

        if shape(translated) != shape(source):
            self.unpair("TABLE_SHAPE_MISMATCH", [translated], [source])
            return
        headers = zip(translated.header, source.header, strict=True)
        for col, (left, right) in enumerate(headers, start=1):
            self.compare_text(
                translated,
                source,
                left,
                right,
                translated_cell=cell_ref(translated.element_id, 0, col),
                source_cell=cell_ref(source.element_id, 0, col),
                line=translated.locator.line_start,
                source_line=source.locator.line_start,
            )
        for left_row, right_row in zip(translated.rows, source.rows, strict=True):
            for left, right in zip(left_row, right_row, strict=True):
                self.compare_text(
                    translated,
                    source,
                    left.text,
                    right.text,
                    translated_cell=cell_ref(translated.element_id, left.row, left.col),
                    source_cell=cell_ref(source.element_id, right.row, right.col),
                    # line 1 of a table is the header, line 2 the separator
                    line=translated.locator.line_start + 1 + left.row,
                    source_line=source.locator.line_start + 1 + right.row,
                )

    def gap(self, translated: Sequence[Element], source: Sequence[Element]) -> None:
        """Elements between two matched skeleton elements."""
        if not translated and not source:
            return
        if any(element.kind in _SKELETON_KINDS for element in (*translated, *source)):
            self.unpair("SKELETON_MISMATCH", translated, source)
        elif [element.kind for element in translated] == [element.kind for element in source]:
            for left, right in zip(translated, source, strict=True):
                self.pair(left, right)
        else:
            self.unpair("SEGMENT_UNALIGNED", translated, source)


def _anchors(translated: Document, source: Document) -> list[tuple[int, int]]:
    """Index pairs of skeleton elements (page markers, headings) that match."""
    left = [
        (index, _skeleton_key(element))
        for index, element in enumerate(translated.elements)
        if element.kind in _SKELETON_KINDS
    ]
    right = [
        (index, _skeleton_key(element))
        for index, element in enumerate(source.elements)
        if element.kind in _SKELETON_KINDS
    ]
    left_keys = [key for _, key in left]
    right_keys = [key for _, key in right]
    if left_keys == right_keys:
        return [(a, b) for (a, _), (b, _) in zip(left, right, strict=True)]
    matcher = SequenceMatcher(None, left_keys, right_keys, autojunk=False)
    anchors: list[tuple[int, int]] = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            anchors.append((left[block.a + offset][0], right[block.b + offset][0]))
    return anchors


def check_translation(
    translated: Document, source: Document
) -> tuple[TranslationCheck, tuple[Finding, ...]]:
    checker = _Checker(translated.language, source.language)
    previous_left = previous_right = -1
    for left_index, right_index in _anchors(translated, source):
        checker.gap(
            translated.elements[previous_left + 1 : left_index],
            source.elements[previous_right + 1 : right_index],
        )
        checker.pair(translated.elements[left_index], source.elements[right_index])
        previous_left, previous_right = left_index, right_index
    checker.gap(
        translated.elements[previous_left + 1 :],
        source.elements[previous_right + 1 :],
    )
    return (
        TranslationCheck(pairs=tuple(checker.pairs), unpaired=tuple(checker.unpaired)),
        tuple(checker.findings),
    )
