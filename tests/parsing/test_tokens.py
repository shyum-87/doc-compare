"""Finding the tokens in a text: numbers, units, signs, codes (spec section 6.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsing.tokens import UNITS, extract_tokens, normalize


def _numbers(text, language="ko"):
    return [token.raw for token in extract_tokens(text, language).numbers]


def _others(text, language="ko"):
    return list(extract_tokens(text, language).others)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("１８０℃", "180°C"),  # full-width digits, one-character unit
        ("５ｋｇ", "5kg"),
        ("−18", "-18"),  # U+2212 minus sign
        ("2〜8", "2~8"),  # U+301C wave dash
        ("2～8", "2~8"),  # U+FF5E full-width tilde
        ("5µm", "5μm"),  # U+00B5 micro sign -> Greek mu
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


def test_numbers_are_found_with_their_value():
    tokens = extract_tokens("오븐 온도는 180℃, 시간은 12.5분으로 한다.", "ko")
    assert [(token.raw, token.value) for token in tokens.numbers] == [
        ("180", Decimal("180")),
        ("12.5", Decimal("12.5")),
    ]


def test_a_number_that_does_not_fit_the_notation_has_no_value():
    tokens = extract_tokens("1,5 kg", "en")
    assert [(token.raw, token.value) for token in tokens.numbers] == [("1,5", None)]
    assert extract_tokens("1,5 kg", "vi").numbers[0].value == Decimal("1.5")


def test_full_width_digits_are_read_as_digits():
    tokens = extract_tokens("１８０℃", "zh")
    assert [(token.raw, token.value) for token in tokens.numbers] == [("180", Decimal("180"))]
    assert tokens.others == ("unit:°C",)


def test_a_sentence_end_is_not_part_of_a_number():
    assert _numbers("기준은 5.") == ["5"]
    assert _numbers("3, 4 그리고 5") == ["3", "4", "5"]


@pytest.mark.parametrize("unit", UNITS)
def test_every_unit_in_the_table_is_found_after_a_number(unit):
    expected = ["unit:" + normalize(unit)]
    assert _others("5" + unit) == expected
    assert _others("5 " + unit) == expected  # one space is allowed


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5 mm", ["unit:mm"]),  # the longest unit wins: not 'm'
        ("5 m", ["unit:m"]),
        ("5 MPa", ["unit:MPa"]),
        ("5  mm", []),  # two spaces
        ("mm 5", []),  # the unit must follow the number
        ("30 min", []),  # 'm' here starts a word
        ("5 Liter", []),
        ("5℃로 한다", ["unit:°C"]),  # a Korean particle may follow
        ("180 °C", ["unit:°C"]),
        ("길이 m", []),
    ],
)
def test_units(text, expected):
    assert _others(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("±1.0%", ["sym:±", "unit:%"]),
        ("2~8℃", ["sym:~", "unit:°C"]),
        ("2〜8℃", ["sym:~", "unit:°C"]),
        ("-18℃이하", ["sym:neg", "unit:°C"]),
        ("−18℃", ["sym:neg", "unit:°C"]),
        ("온도 -5", ["sym:neg"]),
        ("10-20", []),  # a hyphen between numbers is not a sign
        ("2024-11-11", []),
        ("가-나", []),
        ("- 항목", []),
    ],
)
def test_signs(text, expected):
    assert _others(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("WI-BK-204 에 따른다", ["code:WI-BK-204"]),
        ("설비 BK01", ["code:BK01"]),
        ("A-1 구역", ["code:A-1"]),
        ("LotNo.가 없는 원료", []),  # letters only: a word, not a code
        ("Favorites 탭", []),
        ("pH 7", []),
        ("BK01-", ["code:BK01"]),
    ],
)
def test_codes(text, expected):
    assert _others(text) == expected


def test_the_digits_of_a_code_are_not_counted_as_numbers():
    assert _numbers("WI-BK-204 에 따라 3회 확인한다") == ["3"]


def test_text_without_tokens():
    tokens = extract_tokens("원료를 확인한다.", "ko")
    assert tokens.numbers == ()
    assert tokens.others == ()
