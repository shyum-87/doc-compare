"""Blank lines, page markers, headings, paragraphs and where each element is."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import clean_text


def test_blank_lines_make_no_element(parse):
    elements, _ = parse("\n   \n\t\n본문이다.\n\n")
    assert [element.kind for element in elements] == ["paragraph"]
    assert (elements[0].locator.line_start, elements[0].locator.line_end) == (4, 4)


def test_element_ids_follow_the_order_in_the_file(parse):
    elements, _ = parse("[PAGE 1]\n## 1. 개요\n첫 문단이다.\n\n둘째 문단이다.")
    assert [element.element_id for element in elements] == ["e0001", "e0002", "e0003", "e0004"]
    assert [element.locator.line_start for element in elements] == [1, 2, 3, 5]


@pytest.mark.parametrize("line, page", [("[PAGE 8]", 8), ("[PAGE9]", 9), ("  [PAGE 10]  ", 10)])
def test_page_marker(parse, line, page):
    elements, findings = parse(line)
    assert elements[0].kind == "page_marker"
    assert elements[0].page == page
    assert elements[0].locator.page == page
    assert elements[0].raw == line
    assert elements[0].text == line.strip()
    assert findings == ()


def test_a_page_marker_sets_the_page_of_what_follows(parse):
    elements, _ = parse("[PAGE 8]\n첫 쪽 문단이다.\n[PAGE 9]\n다음 쪽 문단이다.")
    assert [element.locator.page for element in elements] == [8, 8, 9, 9]


@pytest.mark.parametrize(
    "line",
    [
        "[PAGE x]",
        "[PAGE 8] 본문",
        "[page 8]",
        "[PAGE  8]",
        "[PAGE 8",
        "  [PAGE x] ",
        "[PAGE 1234567]",
        "[PAGE \N{ARABIC-INDIC DIGIT THREE}]",
    ],
)
def test_a_malformed_page_marker_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].raw == line
    assert elements[1].text == line.strip()
    assert elements[1].locator.page == 1  # it did not change the page
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


def test_a_page_number_of_any_length_cannot_stop_the_parser(parse):
    elements, findings = parse("[PAGE 1]\n[PAGE " + "9" * 5000 + "]")
    assert elements[1].kind == "unclassified"
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line, level, number, title",
    [
        ("## 3. 제조 작업 절차", 2, "3", "제조 작업 절차"),
        ("### 3.1 배합 전 원료 투입 List 조회", 3, "3.1", "배합 전 원료 투입 List 조회"),
        ("#### 3.1.2. 세부 절차", 4, "3.1.2", "세부 절차"),
        ("# 개요", 1, None, "개요"),
        ("## 2024년 생산 계획", 2, None, "2024년 생산 계획"),
    ],
)
def test_heading(parse, line, level, number, title):
    elements, findings = parse("[PAGE 1]\n" + line)
    heading = elements[1]
    assert heading.kind == "heading"
    assert (heading.level, heading.number, heading.title) == (level, number, title)
    assert heading.text == line.lstrip("# ")
    assert findings == ()


@pytest.mark.parametrize(
    "line, number, title, text",
    [
        ("## **3. 제조**", "3", "제조", "3. 제조"),
        ("## **3.** 제조", "3", "제조", "3. 제조"),
        ("### 3.1 **배합** 전<br>조회", "3.1", "배합 전\n조회", "3.1 배합 전\n조회"),
        ("## **주의** 사항", None, "주의 사항", "주의 사항"),
        ("## \N{FULLWIDTH DIGIT THREE}. 제조", None, None, None),
    ],
)
def test_a_heading_is_read_without_its_bold_marks(parse, line, number, title, text):
    if title is None:  # only ASCII digits make a clause number: the whole heading is the title
        title = text = line[3:]
    elements, findings = parse("[PAGE 1]\n" + line)
    heading = elements[1]
    assert heading.kind == "heading"
    assert heading.raw == line
    assert (heading.number, heading.title, heading.text) == (number, title, text)
    assert heading.locator.section_path == (number if number is not None else title,)
    assert findings == ()


def test_the_section_path_follows_the_headings(parse):
    text = "\n".join(
        [
            "[PAGE 1]",
            "첫 제목보다 앞에 있는 문단이다.",
            "## 3. 제조",
            "### 3.1 조회",
            "문단 가.",
            "### 3.2 계량",
            "문단 나.",
            "## 4. 기록",
            "문단 다.",
            "# 부록",
            "문단 라.",
        ]
    )
    elements, _ = parse(text)
    paths = {element.text: element.locator.section_path for element in elements}
    assert paths["첫 제목보다 앞에 있는 문단이다."] == ()
    assert paths["3.1 조회"] == ("3", "3.1")  # a heading is inside its own section
    assert paths["문단 가."] == ("3", "3.1")
    assert paths["문단 나."] == ("3", "3.2")
    assert paths["문단 다."] == ("4",)
    assert paths["문단 라."] == ("부록",)  # no number: the title is used


@pytest.mark.parametrize("line", ["##제목", "####### 일곱 단계", "#", "##"])
def test_a_malformed_heading_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n## 1. 개요\n" + line + "\n문단이다.")
    assert elements[2].kind == "unclassified"
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]
    assert elements[3].locator.section_path == ("1",)  # the section did not change


@pytest.mark.parametrize(
    "mark",
    [
        "\N{ZERO WIDTH NO-BREAK SPACE}",
        "\N{ZERO WIDTH SPACE}",
        "\N{LEFT-TO-RIGHT MARK}",
        "\x00",
    ],
)
@pytest.mark.parametrize("rest", ["[PAGE 9]", "### 3.1 조회", "본문이다."])
def test_a_line_that_starts_with_an_invisible_character_is_not_interpreted(parse, mark, rest):
    elements, findings = parse("[PAGE 8]\n## 3. 제조\n" + mark + rest + "\n문단이다.")
    assert elements[2].kind == "unclassified"
    assert elements[2].raw == mark + rest
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]
    assert findings[0].element_ids == ("e0003",)
    assert elements[3].kind == "paragraph"
    assert elements[3].locator.page == 8  # the hidden marker did not change the page
    assert elements[3].locator.section_path == ("3",)  # nor the section


def test_one_line_is_one_paragraph(parse):
    elements, _ = parse("[PAGE 1]\n첫 줄이다.\n둘째 줄이다.")
    assert [element.kind for element in elements[1:]] == ["paragraph", "paragraph"]
    assert [element.text for element in elements[1:]] == ["첫 줄이다.", "둘째 줄이다."]


def test_raw_keeps_the_line_and_text_is_trimmed(parse):
    line = "  **주의:**LotNo.가 없는 원료는 투입하지 않는다.  "
    elements, _ = parse("[PAGE 1]\n" + line)
    assert elements[1].raw == line
    assert elements[1].text == "주의:LotNo.가 없는 원료는 투입하지 않는다."


def test_typos_are_kept(parse):
    elements, _ = parse("[PAGE 1]\n온도와 상대 습도를 합께 기재한다.")
    assert "합께" in elements[1].text
    assert "합께" in elements[1].raw


@pytest.mark.parametrize(
    "value, expected",
    [
        ("**굵게**", "굵게"),
        ("**주의:**본문", "주의:본문"),
        ("**가** 와 **나**", "가 와 나"),
        ("가<br>나", "가\n나"),
        ("가<BR/>나<br />다", "가\n나\n다"),
        ("**가<br>나**", "가\n나"),
        ("짝이 없는 ** 표시", "짝이 없는 ** 표시"),
        ("2 * 3", "2 * 3"),
    ],
)
def test_clean_text(value, expected):
    assert clean_text(value) == expected
