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
        ("![img021](< img021.png >)", "img021", "img021.png", ""),
        ('![img021](<img021.png "제목" >)', "img021", "img021.png", "제목"),
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
    "line",
    [
        "![img021](<img021.png>) 그림 설명",
        "![img021](img021.png) 그림 설명",
        "![img021]",
        "![img021](img 021.png)",
        "![](",
        "![](img021.png)",  # no image ID: nothing to pair the image by
        "![ ](img021.png)",
        "![img021](< >)",  # no file name
        "![img021](<>)",
        "![img021](<img021.png>",
        "![img021](img021(1).png)",  # parentheses in a file name need the <...> form
    ],
)
def test_a_malformed_image_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "block, kind, lines",
    [
        ('앞 글 ![img1](<img1.png "제목">) 뒤 글', "paragraph", [2]),
        ("- ![img1](img1.png)", "list_item", [2]),
        ("## 3.1 화면 ![img1](img1.png)", "heading", [2]),
        ('|단계|화면|\n|---|---|\n|1|없음|\n|2|![img1](<img1.png "제목">)|', "table", [5]),
        ("|![a](a.png)|![b](b.png)|\n|---|---|\n|![c](c.png)|2|", "table", [2, 4]),
    ],
)
def test_an_image_inside_another_element_is_reported(parse, block, kind, lines):
    # the image is a region that is not read, wherever it stands: one finding per line
    elements, findings = parse("[PAGE 1]\n" + block)
    assert [element.kind for element in elements[1:]] == [kind]
    assert _codes(findings) == ["IMAGE_PRESENT"] * len(lines)
    assert [finding.element_ids for finding in findings] == [("e0002",)] * len(lines)
    assert [(finding.line_start, finding.line_end) for finding in findings] == [
        (line, line) for line in lines
    ]


def test_an_exclamation_mark_before_a_bracket_is_not_an_image(parse):
    elements, findings = parse("[PAGE 1]\n주의![참고] 문서를 본다.")
    assert elements[1].kind == "paragraph"
    assert findings == ()


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
        ("-**주의** 붙여 쓴 굵은 글", "-", "주의 붙여 쓴 굵은 글"),
        ("-\t탭 뒤 항목", "-", "탭 뒤 항목"),
        ("*\N{IDEOGRAPHIC SPACE}전각 공백 뒤 항목", "*", "전각 공백 뒤 항목"),
        # the marker is kept as written, so a digit of any script makes a numbered item
        ("\N{FULLWIDTH DIGIT ONE}) 전각 숫자", "\N{FULLWIDTH DIGIT ONE})", "전각 숫자"),
        ("\N{FULLWIDTH DIGIT TWO}. 전각 숫자와 점", "\N{FULLWIDTH DIGIT TWO}.", "전각 숫자와 점"),
        ("2. 5 kg 투입", "2.", "5 kg 투입"),
        ("1. 2.5 kg 투입", "1.", "2.5 kg 투입"),
        ("1) 2. 확인한다", "1)", "2. 확인한다"),
        ("- 2. 확인한다", "-", "2. 확인한다"),
        ("- -18℃ 이하로 보관", "-", "-18℃ 이하로 보관"),
        ("-三호기 점검", "-", "三호기 점검"),  # a numeral that is a letter, not a number sign
        ("-.env 파일을 확인한다", "-", ".env 파일을 확인한다"),
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


@pytest.mark.parametrize(
    "line",
    [
        "1.",
        "10)",
        "3.2 내용",
        "+ 더하기 표시",
        "*강조* 문장",
        "**굵게** 문장",
        "***굵게*** 문장",
        "**",
        "__",
        "___이름___",
        "<3 kg 이하",
        "<표 1> 참조",
        "\N{MINUS SIGN}18℃ 이하로 보관",
    ],
)
def test_a_line_that_only_looks_like_a_list_item_or_a_rule_is_a_paragraph(parse, line):
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


@pytest.mark.parametrize(
    "line, text",
    [
        ("-**18℃** 이하로 보관", "-18℃ 이하로 보관"),
        ("-.5 kg", "-.5 kg"),
        ("-,5 kg", "-,5 kg"),
        ("-**.**5 kg", "-.5 kg"),
        ("-* 18℃ 이하로 보관", "-* 18℃ 이하로 보관"),
        (
            "-\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT EIGHT}℃",
            "-\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT EIGHT}℃",
        ),
        ("-\N{VULGAR FRACTION ONE HALF} 컵", "-\N{VULGAR FRACTION ONE HALF} 컵"),
    ],
)
def test_a_hyphen_before_a_number_in_another_form_is_not_decided(parse, line, text):
    # bold marks, a decimal point with no zero, and digits of other scripts do not
    # turn the sign into a list marker
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "paragraph"
    assert elements[1].text == text
    assert _codes(findings) == ["AMBIGUOUS_LIST_OR_NEGATIVE"]


def test_a_hyphen_a_space_and_a_digit_is_a_list_item(parse):
    elements, findings = parse("[PAGE 1]\n- 18℃ 이하로 보관한다.")
    assert elements[1].kind == "list_item"
    assert findings == ()


@pytest.mark.parametrize(
    "line",
    [
        "-\N{ZERO WIDTH SPACE}18℃ 이하로 보관",
        "-\N{SOFT HYPHEN}18℃",
        "-\x1f18℃ 이하로 보관",  # a control character that a regular expression takes for a space
        "-**\N{ZERO WIDTH SPACE}18℃**",
        "1.\x1f5 kg 투입",
        "2)\N{ZERO WIDTH SPACE}조회한다",
        "- \N{WORD JOINER}항목",
        "*\x1f항목",
    ],
)
def test_a_hiding_character_next_to_a_list_marker_leaves_the_line_unclassified(parse, line):
    # what the marker is, and whether a sign belongs to a number, would hang on a
    # character that is not seen
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].text == line
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line",
    [
        "2024. 5. 1 개정",
        "1. 2. 항목",
        "3. 4.",
        "1. **2. 항목**",
        "1. \N{FULLWIDTH DIGIT TWO}. 항목",
    ],
)
def test_a_number_and_dot_after_a_number_and_dot_is_not_read_as_a_list_item(parse, line):
    # a date or a run of numbers: the first number is not taken for a list marker
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].text == line
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line",
    [
        "```",
        "```python",
        "~~~",
        "> 인용문",
        ">붙여 쓴 인용문",
        "---",
        "***",
        "___",
        "_____",
        "- - -",
        "* * *",
        "_ _ _",
        "<div>",
        "</table>",
        '<img src="a.png">',
        "<br>로 시작하는 줄",
        "<b>주의</b> 굵게 적은 줄",
        "<!-- 주석 -->",
        "-",
        "--",
        "-- 두 줄표",
        "-*",
        "-**",
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
