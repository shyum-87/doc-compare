"""Damage the Korean sample on purpose and check that the damage is pinpointed.

Line numbers refer to tests/fixtures/rag_ko/sample_bakery_sop.md:
  line 39  |계량중량|전자저울 계량|배합표 대비 ±1.0% 이내|   -> e0017:r2c3
  line 40  the next row of the same table (e0017, lines 36-42)
  line 44  a paragraph (e0018)
  line 56  the heading '### 3.3 ...' (e0024)
"""

from __future__ import annotations

import pytest

from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation

LANGUAGES = ["en", "vi", "zh"]


@pytest.fixture
def check_mutated(make_document, ko_sample, source_samples):
    """check_mutated("vi", mutate) -> (TranslationCheck, findings); mutate edits the line list."""

    def _check(language, mutate):
        lines = list(read_lines(ko_sample).lines)
        mutate(lines)
        translated = make_document(lines, "translated", "ko")
        source = make_document(read_lines(source_samples[language]).lines, "source", language)
        return check_translation(translated, source)

    return _check


def _replace(line_number, old, new):
    def mutate(lines):
        assert old in lines[line_number - 1]
        lines[line_number - 1] = lines[line_number - 1].replace(old, new)

    return mutate


def _delete(line_number):
    def mutate(lines):
        del lines[line_number - 1]

    return mutate


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_number_is_pinpointed(check_mutated, language):
    result, findings = check_mutated(language, _replace(39, "±1.0%", "±2.0%"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0017",)
    assert finding.counterpart_element_ids == ("e0017",)
    assert finding.cell_ref == "e0017:r2c3"
    assert (finding.line_start, finding.line_end) == (39, 39)
    # the source token is shown as it is written in the source language
    source_token = "num:1,0" if language == "vi" else "num:1.0"
    assert finding.missing_tokens == (source_token,)
    assert finding.extra_tokens == ("num:2.0",)

    assert len(result.pairs) == 120
    assert [pair.translated_ref for pair in result.pairs if pair.status != "match"] == [
        "e0017:r2c3"
    ]
    assert result.unpaired == ()


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_unit_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(39, "±1.0%", "±1.0℃"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].cell_ref == "e0017:r2c3"
    assert (findings[0].line_start, findings[0].line_end) == (39, 39)
    assert findings[0].missing_tokens == ("unit:%",)
    assert findings[0].extra_tokens == ("unit:°C",)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_dropped_minus_sign_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(103, "-18℃", "18℃"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].cell_ref == "e0042:r4c2"
    assert (findings[0].line_start, findings[0].line_end) == (103, 103)
    assert findings[0].missing_tokens == ("sym:neg",)
    assert findings[0].extra_tokens == ()


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_code_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(52, "WI-BK-204", "WI-BK-205"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].element_ids == ("e0022",)
    assert findings[0].cell_ref is None
    assert (findings[0].line_start, findings[0].line_end) == (52, 52)
    assert findings[0].missing_tokens == ("code:WI-BK-204",)
    assert findings[0].extra_tokens == ("code:WI-BK-205",)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_table_row_is_pinpointed(check_mutated, language):
    result, findings = check_mutated(language, _delete(40))
    assert [finding.code for finding in findings] == ["TABLE_SHAPE_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0017",)
    assert finding.counterpart_element_ids == ("e0017",)
    assert (finding.line_start, finding.line_end) == (36, 41)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "TABLE_SHAPE_MISMATCH"
    # the 18 cells of that table are not compared; everything else still is
    assert len(result.pairs) == 120 - 18
    assert {pair.status for pair in result.pairs} == {"match"}


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_paragraph_is_narrowed_to_its_segment(check_mutated, language):
    result, findings = check_mutated(language, _delete(44))
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    # everything between the heading 3.2 and the page marker of page 10
    assert finding.element_ids == ("e0016", "e0017", "e0018", "e0019", "e0020", "e0021")
    assert finding.counterpart_element_ids == (
        "e0016",
        "e0017",
        "e0018",
        "e0019",
        "e0020",
        "e0021",
        "e0022",
    )
    assert (finding.line_start, finding.line_end) == (34, 51)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "SEGMENT_UNALIGNED"
    assert {pair.status for pair in result.pairs} == {"match"}
    # the page marker of page 10 is paired again: one element earlier in the translation
    assert ("e0022", "e0023") in [(pair.translated_ref, pair.source_ref) for pair in result.pairs]


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_heading_is_a_skeleton_mismatch(check_mutated, language):
    result, findings = check_mutated(language, _delete(56))
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    # everything between the page markers of page 10 and page 11
    assert finding.element_ids == tuple(f"e{n:04d}" for n in range(24, 35))
    assert finding.counterpart_element_ids == tuple(f"e{n:04d}" for n in range(24, 36))
    assert (finding.line_start, finding.line_end) == (57, 85)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "SKELETON_MISMATCH"
    assert {pair.status for pair in result.pairs} == {"match"}
    assert ("e0035", "e0036") in [(pair.translated_ref, pair.source_ref) for pair in result.pairs]


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_page_number_is_a_skeleton_mismatch(check_mutated, language):
    _, findings = check_mutated(language, _replace(54, "[PAGE 10]", "[PAGE 12]"))
    assert "SKELETON_MISMATCH" in [finding.code for finding in findings]
    assert {finding.grade for finding in findings} == {"review_required"}
