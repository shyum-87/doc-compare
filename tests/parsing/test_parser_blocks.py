"""Images, list items, the '-18' ambiguity and lines that are left unclassified."""

from __future__ import annotations

import pytest


def _codes(findings):
    return [finding.code for finding in findings]


@pytest.mark.parametrize(
    "line, image_id, file_name, title",
    [
        (
            '![img021](<img021.png "원료 투입 List 조회 화면">)',
            "img021",
            "img021.png",
            "원료 투입 List 조회 화면",
        ),
        ("![img021](<img021.png>)", "img021", "img021.png", ""),
        ('![img021](img021.png "조회 화면")', "img021", "img021.png", "조회 화면"),
        ("![img021](img021.png)", "img021", "img021.png", ""),
        ('![img 021](<조회 화면.png "제목">)', "img 021", "조회 화면.png", "제목"),
    ],
)
def test_image(parse, line, image_id, file_name, title):
    elements, findings = parse("[PAGE 1]\n" + line)
    image = elements[1]
    assert image.kind == "image"
    assert (image.image_id, image.file_name, image.title) == (image_id, file_name, title)
    assert image.text == title
    assert image.raw == line
    assert _codes(findings) == ["IMAGE_PRESENT"]
    assert findings[0].grade == "info"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


@pytest.mark.parametrize(
    "line", ["![img021](<img021.png>) 그림 설명", "![img021]", "![img021](img 021.png)", "![]("]
)
def test_a_malformed_image_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line, marker, text",
    [
        ("1) Favorites 탭에서 메뉴를 선택한다.", "1)", "Favorites 탭에서 메뉴를 선택한다."),
        ("2)조회 조건을 입력한다.", "2)", "조회 조건을 입력한다."),
        ("12) 열두째 단계", "12)", "열두째 단계"),
        ("1. 첫째 항목", "1.", "첫째 항목"),
        ("- 보관고 온도는 매일 1회 이상 확인한다", "-", "보관고 온도는 매일 1회 이상 확인한다"),
        ("* 별표 항목", "*", "별표 항목"),
        ("-붙여 쓴 항목", "-", "붙여 쓴 항목"),
        ("  - **주의** 들여 쓴 항목", "-", "주의 들여 쓴 항목"),
    ],
)
def test_list_item(parse, line, marker, text):
    elements, findings = parse("[PAGE 1]\n" + line)
    item = elements[1]
    assert item.kind == "list_item"
    assert (item.marker, item.text) == (marker, text)
    assert item.raw == line
    assert findings == ()


def test_each_list_line_is_its_own_element(parse):
    elements, _ = parse("[PAGE 1]\n1) 가\n2) 나\n3) 다")
    assert [element.kind for element in elements[1:]] == ["list_item"] * 3
    assert [element.locator.line_start for element in elements[1:]] == [2, 3, 4]


@pytest.mark.parametrize("line", ["3.5 이상 발생시 조치", "2024년 계획이다.", "1.5배로 늘린다."])
def test_a_line_that_starts_with_a_number_is_a_paragraph(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "paragraph"
    assert findings == ()


@pytest.mark.parametrize("line", ["-18℃ 이하로 보관한다.", "-5 ~ 0℃", "-18"])
def test_a_hyphen_before_a_digit_is_not_decided(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "paragraph"
    assert elements[1].text == line  # the hyphen stays in the text
    assert _codes(findings) == ["AMBIGUOUS_LIST_OR_NEGATIVE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


def test_a_hyphen_a_space_and_a_digit_is_a_list_item(parse):
    elements, findings = parse("[PAGE 1]\n- 18℃ 이하로 보관한다.")
    assert elements[1].kind == "list_item"
    assert findings == ()


@pytest.mark.parametrize(
    "line",
    [
        "```",
        "```python",
        "~~~",
        "> 인용문",
        "---",
        "***",
        "_____",
        "<div>",
        "</table>",
        '<img src="a.png">',
        "-",
        "--",
        "-- 두 줄표",
    ],
)
def test_structural_lines_that_are_not_interpreted(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].text == line
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]
    assert findings[0].grade == "review_required"


def test_an_unclassified_line_does_not_hide_its_neighbours(parse):
    elements, findings = parse("[PAGE 1]\n앞 문단이다.\n> 인용문\n뒤 문단이다.")
    assert [element.kind for element in elements[1:]] == ["paragraph", "unclassified", "paragraph"]
    assert [finding.line_start for finding in findings] == [3]
