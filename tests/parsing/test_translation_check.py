"""Checking a Korean translation against its source (spec section 6)."""

from __future__ import annotations

import pytest

from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation


@pytest.fixture
def check(make_document):
    """check(korean_lines, source_lines, "en") -> (TranslationCheck, findings)"""

    def _check(translated_lines, source_lines, source_language="en"):
        translated = make_document(translated_lines, "translated", "ko")
        source = make_document(source_lines, "source", source_language)
        return check_translation(translated, source)

    return _check


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_the_sample_translation_matches_its_source(
    make_document, ko_sample, source_samples, language
):
    translated = make_document(read_lines(ko_sample).lines, "translated", "ko")
    source = make_document(read_lines(source_samples[language]).lines, "source", language)
    result, findings = check_translation(translated, source)
    assert len(result.pairs) == 120
    assert {pair.status for pair in result.pairs} == {"match"}
    assert result.unpaired == ()
    assert findings == ()


def test_elements_are_paired_in_order(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단이다.", "", "- 항목"],
        ["[PAGE 1]", "## 1 Overview", "", "A paragraph.", "", "- An item"],
    )
    assert [(pair.translated_ref, pair.source_ref, pair.status) for pair in result.pairs] == [
        ("e0001", "e0001", "match"),  # page markers are anchors and count as pairs
        ("e0002", "e0002", "match"),
        ("e0003", "e0003", "match"),
        ("e0004", "e0004", "match"),
    ]
    assert result.unpaired == ()
    assert findings == ()


def test_a_changed_number_in_a_paragraph(check):
    result, findings = check(
        ["[PAGE 1]", "오븐 온도는 190℃로 한다."],
        ["[PAGE 1]", "Set the oven temperature to 180℃."],
    )
    pair = result.pairs[1]
    assert (pair.translated_ref, pair.source_ref) == ("e0002", "e0002")
    assert pair.status == "token_mismatch"
    assert pair.missing_tokens == ("num:180",)
    assert pair.extra_tokens == ("num:190",)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "TOKEN_MISMATCH"
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0002",)
    assert finding.counterpart_element_ids == ("e0002",)
    assert finding.cell_ref is None
    assert (finding.line_start, finding.line_end) == (2, 2)
    assert finding.missing_tokens == ("num:180",)
    assert finding.extra_tokens == ("num:190",)


def test_the_title_of_a_heading_is_compared(check):
    _, findings = check(
        ["[PAGE 1]", "## 2 굽기 180℃"],
        ["[PAGE 1]", "## 2 Baking at 190℃"],
    )
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].missing_tokens == ("num:190",)


def test_the_source_notation_follows_its_language(check):
    lines = ["[PAGE 1]", "1,5 kg"]
    assert check(["[PAGE 1]", "1.5 kg"], lines, "vi")[1] == ()
    assert [finding.code for finding in check(["[PAGE 1]", "1.5 kg"], lines, "en")[1]] == [
        "TOKEN_MISMATCH",
        "NUMBER_FORMAT_AMBIGUOUS",
    ]


def test_an_ambiguous_number_is_reported_on_its_own_side(check):
    _, findings = check(["[PAGE 1]", "", "1.5 kg"], ["[PAGE 1]", "1,5 kg"], "en")
    ambiguous = findings[1]
    assert ambiguous.code == "NUMBER_FORMAT_AMBIGUOUS"
    assert ambiguous.grade == "review_required"
    assert ambiguous.document == "source"
    assert ambiguous.element_ids == ("e0002",)
    assert ambiguous.counterpart_element_ids == ("e0002",)
    assert (ambiguous.line_start, ambiguous.line_end) == (2, 2)  # a line of the source file
    assert (ambiguous.missing_tokens, ambiguous.extra_tokens) == ((), ())

    _, findings = check(["[PAGE 1]", "", "1,5 kg"], ["[PAGE 1]", "1.5 kg"], "en")
    assert [(finding.code, finding.document) for finding in findings] == [
        ("TOKEN_MISMATCH", "translated"),
        ("NUMBER_FORMAT_AMBIGUOUS", "translated"),
    ]
    assert (findings[1].line_start, findings[1].line_end) == (3, 3)


def test_a_different_order_of_kinds_leaves_the_whole_segment_unpaired(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단이다.", "", "- 항목", "", "[PAGE 2]", "끝 문단."],
        ["[PAGE 1]", "## 1 Overview", "", "- An item", "", "A paragraph.", "", "[PAGE 2]", "End."],
    )
    assert len(result.unpaired) == 1
    segment = result.unpaired[0]
    assert segment.reason == "SEGMENT_UNALIGNED"
    assert segment.translated_element_ids == ("e0003", "e0004")
    assert segment.source_element_ids == ("e0003", "e0004")
    # the segments before and after it are still paired
    assert [pair.translated_ref for pair in result.pairs] == ["e0001", "e0002", "e0005", "e0006"]

    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0003", "e0004")
    assert finding.counterpart_element_ids == ("e0003", "e0004")
    assert (finding.line_start, finding.line_end) == (4, 6)


def test_content_missing_from_the_translation(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요"],
        ["[PAGE 1]", "## 1 Overview", "", "A paragraph only the source has."],
    )
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ()  # nothing on the translated side to point at
    assert finding.counterpart_element_ids == ("e0003",)
    assert (finding.line_start, finding.line_end) == (None, None)
    assert result.unpaired[0].translated_element_ids == ()
    assert result.unpaired[0].source_element_ids == ("e0003",)


def test_images_pair_only_with_the_same_id(check):
    result, findings = check(
        ["[PAGE 1]", "앞 문단.", "", '![img001](<img001.png "화면">)', "", "뒤 문단."],
        ["[PAGE 1]", "Before.", "", '![img002](<img002.png "Screen">)', "", "After."],
    )
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    assert findings[0].element_ids == ("e0003",)
    assert findings[0].counterpart_element_ids == ("e0003",)
    assert (findings[0].line_start, findings[0].line_end) == (4, 4)
    assert [pair.translated_ref for pair in result.pairs] == ["e0001", "e0002", "e0004"]

    result, findings = check(
        ["[PAGE 1]", '![img001](<img001.png "화면">)'],
        ["[PAGE 1]", '![img001](<img001.png "Screen">)'],
    )
    assert findings == ()
    assert [pair.status for pair in result.pairs] == ["match", "match"]


TABLE_KO = ["[PAGE 1]", "", "|구분|기준|", "|---|---|", "|온도|2~8℃|", "|중량|±1.0%|"]
TABLE_EN = ["[PAGE 1]", "|Item|Limit|", "|---|---|", "|Temperature|2~8℃|", "|Weight|±1.0%|"]


def test_table_cells_are_paired_one_by_one(check):
    result, findings = check(TABLE_KO, TABLE_EN)
    assert findings == ()
    assert [(pair.translated_ref, pair.source_ref) for pair in result.pairs[1:]] == [
        ("e0002:r0c1", "e0002:r0c1"),  # row 0 is the header
        ("e0002:r0c2", "e0002:r0c2"),
        ("e0002:r1c1", "e0002:r1c1"),
        ("e0002:r1c2", "e0002:r1c2"),
        ("e0002:r2c1", "e0002:r2c1"),
        ("e0002:r2c2", "e0002:r2c2"),
    ]


def test_a_changed_cell_is_located_by_cell_and_line(check):
    translated = [*TABLE_KO[:5], "|중량|±2.0%|"]
    result, findings = check(translated, TABLE_EN)
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    finding = findings[0]
    assert finding.element_ids == ("e0002",)
    assert finding.cell_ref == "e0002:r2c2"
    assert (finding.line_start, finding.line_end) == (6, 6)  # the line of that row
    assert finding.missing_tokens == ("num:1.0",)
    assert finding.extra_tokens == ("num:2.0",)
    assert [pair.translated_ref for pair in result.pairs if pair.status != "match"] == [
        "e0002:r2c2"
    ]


def test_a_changed_header_cell_is_on_the_first_line_of_the_table(check):
    translated = ["[PAGE 1]", "", "|구분 1|기준|", *TABLE_KO[3:]]
    _, findings = check(translated, TABLE_EN)
    assert [finding.cell_ref for finding in findings] == ["e0002:r0c1"]
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_an_ambiguous_number_in_a_source_cell_points_at_the_source_line(check):
    source = [*TABLE_EN[:4], "|Weight|±1,0%|"]
    _, findings = check(TABLE_KO, source, "en")
    assert [(finding.code, finding.document) for finding in findings] == [
        ("TOKEN_MISMATCH", "translated"),
        ("NUMBER_FORMAT_AMBIGUOUS", "source"),
    ]
    assert findings[0].cell_ref == "e0002:r2c2"
    assert (findings[0].line_start, findings[0].line_end) == (6, 6)
    assert findings[1].cell_ref == "e0002:r2c2"
    assert (findings[1].line_start, findings[1].line_end) == (5, 5)


@pytest.mark.parametrize(
    "translated",
    [
        TABLE_KO[:5],  # one row fewer
        [*TABLE_KO, "|습도|60%|"],  # one row more
        ["[PAGE 1]", "", "|구분|기준|비고|", "|---|---|---|", "|온도|2~8℃|-|", "|중량|±1.0%|-|"],
    ],
)
def test_tables_of_a_different_shape_are_not_paired(check, translated):
    result, findings = check(translated, TABLE_EN)
    assert [finding.code for finding in findings] == ["TABLE_SHAPE_MISMATCH"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0002",)
    assert finding.counterpart_element_ids == ("e0002",)
    assert finding.cell_ref is None
    assert finding.line_start == 3
    assert [pair.translated_ref for pair in result.pairs] == ["e0001"]  # no cell was compared
    assert [segment.reason for segment in result.unpaired] == ["TABLE_SHAPE_MISMATCH"]


def test_a_missing_heading_leaves_its_surroundings_unpaired(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단 1.", "", "문단 2.", "", "[PAGE 2]", "끝 문단."],
        ["[PAGE 1]", "## 1 Overview", "", "One.", "", "## 2 Scope", "", "Two.", "[PAGE 2]", "End."],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0003", "e0004")
    assert finding.counterpart_element_ids == ("e0003", "e0004", "e0005")
    assert (finding.line_start, finding.line_end) == (4, 6)
    assert [segment.reason for segment in result.unpaired] == ["SKELETON_MISMATCH"]
    # the matching page markers and headings around it still anchor the rest
    assert [(pair.translated_ref, pair.source_ref) for pair in result.pairs] == [
        ("e0001", "e0001"),
        ("e0002", "e0002"),
        ("e0005", "e0006"),
        ("e0006", "e0007"),
    ]


def test_a_different_page_number_is_a_skeleton_mismatch(check):
    result, findings = check(
        ["[PAGE 1]", "문단 1.", "", "[PAGE 2]", "문단 2."],
        ["[PAGE 1]", "One.", "", "[PAGE 3]", "Two."],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert findings[0].element_ids == ("e0002", "e0003", "e0004")
    assert findings[0].counterpart_element_ids == ("e0002", "e0003", "e0004")
    assert [pair.translated_ref for pair in result.pairs] == ["e0001"]


def test_a_different_heading_number_is_a_skeleton_mismatch(check):
    _, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "## 2 범위"],
        ["[PAGE 1]", "## 1 Overview", "", "## 3 Scope"],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert findings[0].element_ids == ("e0003",)
    assert findings[0].counterpart_element_ids == ("e0003",)


def test_documents_with_nothing_in_common(check):
    result, findings = check(["문단이다."], ["[PAGE 1]", "A paragraph."])
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert result.pairs == ()
    assert result.unpaired[0].translated_element_ids == ("e0001",)
    assert result.unpaired[0].source_element_ids == ("e0001", "e0002")
