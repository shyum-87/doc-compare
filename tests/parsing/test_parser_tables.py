"""Tables: one element per table, cells addressed by row and column."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import split_table_row

TABLE = "\n".join(
    [
        "[PAGE 9]",
        "### 3.2 계량",
        "",
        "|확인 항목|확인 방법|판정기준|",
        "|---|---|---|",
        "|품번|List와 원료 Label 대조|일치|",
        "|계량중량|전자저울 계량|배합표 대비 ±1.0% 이내|",
        "",
        "표 다음 문단이다.",
    ]
)


def test_a_table_is_one_element(parse):
    elements, findings = parse(TABLE)
    assert [element.kind for element in elements] == [
        "page_marker",
        "heading",
        "table",
        "paragraph",
    ]
    table = elements[2]
    assert table.element_id == "e0003"
    assert table.table_index == 1
    assert (table.locator.line_start, table.locator.line_end) == (4, 7)
    assert table.locator.page == 9
    assert table.locator.section_path == ("3.2",)
    assert table.header == ("확인 항목", "확인 방법", "판정기준")
    assert findings == ()


def test_cells_carry_their_row_and_column(parse):
    table = parse(TABLE)[0][2]
    assert len(table.rows) == 2
    assert [(cell.row, cell.col) for cell in table.rows[1]] == [(2, 1), (2, 2), (2, 3)]
    assert table.rows[1][2].text == "배합표 대비 ±1.0% 이내"


def test_raw_keeps_the_table_lines_and_text_drops_the_separator(parse):
    table = parse(TABLE)[0][2]
    assert table.raw == "\n".join(TABLE.split("\n")[3:7])
    assert table.text == "\n".join(
        [
            "확인 항목 | 확인 방법 | 판정기준",
            "품번 | List와 원료 Label 대조 | 일치",
            "계량중량 | 전자저울 계량 | 배합표 대비 ±1.0% 이내",
        ]
    )


def test_tables_are_numbered_in_order(parse):
    elements, _ = parse("[PAGE 1]\n|가|나|\n|---|---|\n|1|2|\n\n|다|라|\n|:--|--:|\n|3|4|")
    tables = [element for element in elements if element.kind == "table"]
    assert [table.table_index for table in tables] == [1, 2]
    assert [table.locator.line_start for table in tables] == [2, 6]


def test_a_table_may_have_no_data_rows(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|---|---|")
    assert elements[1].kind == "table"
    assert elements[1].rows == ()
    assert findings == ()


def test_markup_inside_cells_is_cleaned(parse):
    elements, _ = parse("[PAGE 1]\n|**구분**|기준|\n|---|---|\n|온도|2~8℃<br>냉장|")
    table = elements[1]
    assert table.header == ("구분", "기준")
    assert table.rows[0][1].text == "2~8℃\n냉장"
    assert "<br>" in table.raw


def test_a_row_with_a_different_number_of_cells(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|다|\n|---|---|---|\n|1|2|3|\n|4|5|\n|6|7|8|9|")
    table = elements[1]
    assert table.kind == "table"
    assert [len(row) for row in table.rows] == [3, 2, 4]  # kept as written, nothing is padded
    assert [finding.code for finding in findings] == ["TABLE_ROW_WIDTH_MISMATCH"] * 2
    assert [finding.grade for finding in findings] == ["review_required"] * 2
    assert [finding.element_ids for finding in findings] == [("e0002",), ("e0002",)]
    assert [finding.line_start for finding in findings] == [5, 6]


def test_a_separator_with_a_different_number_of_cells(parse):
    _, findings = parse("[PAGE 1]\n|가|나|다|\n|---|---|\n|1|2|3|")
    assert [finding.code for finding in findings] == ["TABLE_ROW_WIDTH_MISMATCH"]
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_pipe_lines_without_a_separator_are_unclassified(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|1|2|\n문단이다.")
    assert [element.kind for element in elements[1:]] == [
        "unclassified",
        "unclassified",
        "paragraph",
    ]
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"] * 2
    assert [finding.line_start for finding in findings] == [2, 3]


def test_indented_pipe_lines_without_a_separator_keep_raw_as_written(parse):
    elements, _ = parse("[PAGE 1]\n  |가|나|\n  |1|2|  ")
    assert [element.text for element in elements[1:]] == ["|가|나|", "|1|2|"]
    assert [element.raw for element in elements[1:]] == ["  |가|나|", "  |1|2|  "]


def test_a_single_pipe_line_is_unclassified(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|")
    assert elements[1].kind == "unclassified"
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line, cells",
    [
        ("|가|나|", ["가", "나"]),
        ("| 가 | 나 |  ", ["가", "나"]),
        ("|가||다|", ["가", "", "다"]),
        ("|가|나", ["가", "나"]),
        (r"|가|나\|다|", ["가", "나|다"]),
        (r"|가|나\|", ["가", "나|"]),  # the last pipe is escaped: it closes nothing
        ("|**가**|1<br>2|", ["가", "1\n2"]),
    ],
)
def test_split_table_row(line, cells):
    assert split_table_row(line) == cells


@pytest.mark.parametrize("separator", ["|-|-|", "| :--- | ---: |", "|:-:|---|", "|---|---"])
def test_separator_rows(parse, separator):
    elements, findings = parse("[PAGE 1]\n|가|나|\n" + separator + "\n|1|2|")
    assert elements[1].kind == "table"
    assert elements[1].rows[0][1].text == "2"
    assert findings == ()


@pytest.mark.parametrize(
    "second_line",
    [
        "|---|나|",  # one cell is not dashes
        "|---x|---|",  # dashes with something after them
        "||",  # no dashes at all
    ],
)
def test_a_second_line_that_is_not_a_separator_makes_no_table(parse, second_line):
    elements, findings = parse("[PAGE 1]\n|가|나|\n" + second_line + "\n|1|2|")
    assert [element.kind for element in elements[1:]] == ["unclassified"] * 3
    assert [element.text for element in elements[1:]] == ["|가|나|", second_line, "|1|2|"]
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"] * 3


def test_an_indented_table_is_read_and_raw_keeps_the_lines_as_written(parse):
    lines = ["  |가|나|", "  |---|---|", "  |1|2|  "]
    elements, findings = parse("[PAGE 1]\n" + "\n".join(lines))
    table = elements[1]
    assert table.kind == "table"
    assert table.raw == "\n".join(lines)
    assert table.rows[0][1].text == "2"
    assert findings == ()


def test_a_separator_with_more_cells_than_the_header(parse):
    _, findings = parse("[PAGE 1]\n|가|나|\n|---|---|---|\n|1|2|")
    assert [finding.code for finding in findings] == ["TABLE_ROW_WIDTH_MISMATCH"]
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


@pytest.mark.parametrize("mark", ["\x0c", "\x85", "\N{LINE SEPARATOR}"])
def test_a_row_that_other_tools_would_break_in_two_ends_the_table(parse, mark):
    row = "|3|4|" + mark + "### 3.3 보관"
    elements, findings = parse("[PAGE 1]\n|가|나|\n|---|---|\n|1|2|\n" + row + "\n|5|6|")
    assert [element.kind for element in elements[1:]] == ["table", "unclassified", "unclassified"]
    assert len(elements[1].rows) == 1
    assert elements[1].locator.line_end == 4
    assert elements[2].raw == row
    assert [(finding.code, finding.line_start) for finding in findings] == [
        ("UNCLASSIFIED_LINE", 5),
        ("UNCLASSIFIED_LINE", 6),
    ]


@pytest.mark.parametrize("row", ["|1|2|\x0c", "\x0c|1|2|"])
def test_a_break_character_at_either_end_of_a_row_is_trimmed_like_a_space(parse, row):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|---|---|\n" + row)
    assert elements[1].kind == "table"
    assert elements[1].rows[0][1].text == "2"
    assert findings == ()


def test_a_second_separator_row_leaves_the_whole_block_unclassified(parse):
    # two tables may have run together: neither is guessed
    text = "[PAGE 1]\n|가|나|\n|---|---|\n|1|2|\n|다|라|\n|---|---|\n|3|4|\n\n|마|바|\n|---|---|"
    elements, findings = parse(text)
    assert [element.kind for element in elements[1:]] == ["unclassified"] * 6 + ["table"]
    assert elements[-1].table_index == 1
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"] * 6
    assert [finding.line_start for finding in findings] == [2, 3, 4, 5, 6, 7]


def test_a_data_row_of_dashes_counts_as_a_second_separator(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|---|---|\n| - | - |")
    assert [element.kind for element in elements[1:]] == ["unclassified"] * 3
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"] * 3
