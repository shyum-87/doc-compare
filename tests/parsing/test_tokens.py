"""Finding the tokens in a text: numbers, units, signs, codes (spec section 6.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsing.tokens import UNIT_SPELLINGS, UNITS, extract_tokens, normalize


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
        ("\N{HYPHEN}18", "-18"),
        ("WI\N{NON-BREAKING HYPHEN}BK", "WI-BK"),
        ("\N{FIGURE DASH}18", "-18"),
        ("\N{EN DASH}18", "-18"),
        ("\N{FULLWIDTH HYPHEN-MINUS}18", "-18"),
        ("2\N{TILDE OPERATOR}8", "2~8"),
        ("5\N{EM DASH}10", "5\N{EM DASH}10"),  # left alone
        ("10³", "10^3"),
        ("10⁹", "10^9"),
        ("10⁻³", "10^-3"),
        ("10⁺²³", "10^+23"),  # one mark for the whole run
        ("x⁰¹²³⁴⁵⁶⁷⁸⁹", "x^0123456789"),
        ("5 m² 와 3 m³", "5 m^2 와 3 m^3"),
        ("H₂O", "H2O"),  # a subscript is not marked
        ("5㎖", "5ml"),
        ("5ℓ", "5l"),
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


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,234,567", ["1,234,567"]),  # one number, however many separators
        ("1.2.3", ["1.2.3"]),
        ("1.000,5", ["1.000,5"]),
        ("09:30", ["09", "30"]),
        ("5..7", ["5", ".7"]),
        ("5,,7", ["5", "7"]),
    ],
)
def test_where_a_number_ends(text, expected):
    assert _numbers(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10³ CFU/g", ["10", "3"]),  # not 103
        ("1.5×10⁵", ["1.5", "10", "5"]),
        ("10⁻³", ["10", "3"]),
        ("180¹ 참조", ["180", "1"]),  # a footnote mark
        ("5 m²", ["5", "2"]),
    ],
)
def test_a_superscript_is_not_part_of_the_number_before_it(text, expected):
    assert _numbers(text) == expected


def test_a_superscript_sign_and_a_unit_before_a_superscript_are_kept():
    assert _others("10⁻³") == ["sym:neg"]
    assert _others("5 m²") == ["unit:m"]
    assert _others("CO₂ 5%") == ["code:CO2", "unit:%"]


@pytest.mark.parametrize(
    "text, numbers, others",
    [
        (".5 kg", [(".5", None)], ["unit:kg"]),
        ("-.5 kg", [(".5", None)], ["sym:neg", "unit:kg"]),
        ("약 .25 mL", [(".25", None)], ["unit:mL"]),
        ("(.5)", [(".5", None)], []),
        (".5.5", [(".5.5", None)], []),
        ("A-.5", [(".5", None)], []),  # the hyphen follows a letter: not a sign
        ("No.5", [("5", Decimal("5"))], []),  # the point follows a letter
        ("한다.5분간", [("5", Decimal("5"))], []),
        ("BK01.5", [("5", Decimal("5"))], ["code:BK01"]),
        ("1.5", [("1.5", Decimal("1.5"))], []),
        (". 5", [("5", Decimal("5"))], []),
        (".", [], []),
        ("-.", [], []),
        (".\N{ARABIC-INDIC DIGIT FIVE}", [], []),  # only an ASCII digit is a digit here
        (",5", [("5", Decimal("5"))], []),  # only a point leads a number
    ],
)
def test_a_point_that_leads_a_number_stays_with_it(text, numbers, others):
    tokens = extract_tokens(text, "ko")
    assert [(token.raw, token.value) for token in tokens.numbers] == numbers
    assert list(tokens.others) == others


@pytest.mark.parametrize("unit", UNITS)
def test_every_unit_in_the_table_is_found_after_a_number(unit):
    expected = ["unit:" + normalize(unit)]
    assert _others("5" + unit) == expected
    assert _others("5 " + unit) == expected  # one space is allowed


def test_another_spelling_gives_the_unit_of_the_table():
    assert UNIT_SPELLINGS == {"ml": "mL", "l": "L"}
    for spelling, unit in UNIT_SPELLINGS.items():
        assert unit in UNITS
        assert _others("5" + spelling) == ["unit:" + unit]
        assert _others("5 " + spelling) == ["unit:" + unit]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5 mm", ["unit:mm"]),  # the longest unit wins: not 'm'
        ("5 m", ["unit:m"]),
        ("5 MPa", ["unit:MPa"]),
        ("5  mm", []),  # two spaces
        ("5\tmm", []),  # a tab is not the one space
        ("5\N{NO-BREAK SPACE}mm", ["unit:mm"]),  # NFKC turns it into a space
        ("mm 5", []),  # the unit must follow the number
        ("30 min", []),  # 'm' here starts a word
        ("2 ms", []),  # also when the word ends the text
        ("5 Liter", []),
        ("5 mmol", []),
        ("5 kgf", []),
        ("5 mẻ", []),  # a letter with a tone mark is a letter
        ("5 gói", []),
        ("5 lần", []),
        ("5℃로 한다", ["unit:°C"]),  # a Korean particle may follow
        ("5mm的", ["unit:mm"]),
        ("180 °C", ["unit:°C"]),
        ("길이 m", []),
        ("5㎖", ["unit:mL"]),
        ("5ℓ", ["unit:L"]),
        ("5㎏", ["unit:kg"]),
        ("5 mL/min", ["unit:mL"]),
        ("5 Kg", []),  # not in the table as written
    ],
)
def test_units(text, expected):
    assert _others(text) == expected


def test_scanning_goes_on_after_the_unit():
    tokens = extract_tokens("5m2", "ko")
    assert [token.raw for token in tokens.numbers] == ["5", "2"]
    assert tokens.others == ("unit:m",)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("±1.0%", ["sym:±", "unit:%"]),
        ("2~8℃", ["sym:~", "unit:°C"]),
        ("2〜8℃", ["sym:~", "unit:°C"]),
        ("2\N{TILDE OPERATOR}8℃", ["sym:~", "unit:°C"]),
        ("-18℃이하", ["sym:neg", "unit:°C"]),
        ("−18℃", ["sym:neg", "unit:°C"]),
        ("\N{EN DASH}18 °C", ["sym:neg", "unit:°C"]),
        ("\N{HYPHEN}18", ["sym:neg"]),
        ("온도 -5", ["sym:neg"]),
        ("영하-5", ["sym:neg"]),  # after Hangul
        ("(-18℃)", ["sym:neg", "unit:°C"]),
        ("-20~-18℃", ["sym:neg", "sym:~", "sym:neg", "unit:°C"]),
        ("10-20", []),  # a hyphen between numbers is not a sign
        ("2\N{EN DASH}8 °C", ["unit:°C"]),
        ("2024-11-11", []),
        ("5 mm-10 mm", ["unit:mm", "unit:mm"]),  # after a letter
        ("가-나", []),
        ("- 항목", []),
        ("- 18", []),  # a space between the sign and the number
        ("\N{EM DASH}18", []),  # the em dash is not folded
    ],
)
def test_signs(text, expected):
    assert _others(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("WI-BK-204 에 따른다", ["code:WI-BK-204"]),
        ("WI\N{NON-BREAKING HYPHEN}BK\N{NON-BREAKING HYPHEN}204", ["code:WI-BK-204"]),
        ("설비 BK01", ["code:BK01"]),
        ("A-1 구역", ["code:A-1"]),
        ("IMG_021", ["code:IMG_021"]),
        ("LotNo.가 없는 원료", []),  # letters only: a word, not a code
        ("Favorites 탭", []),
        ("pH 7", []),
        ("BK01-", ["code:BK01"]),
        ("BK01_", ["code:BK01"]),
        ("BK01-_-", ["code:BK01"]),
        ("Bước2", ["code:c2"]),  # the run starts after the letter with a tone mark
    ],
)
def test_codes(text, expected):
    assert _others(text) == expected


def test_the_digits_of_a_code_are_not_counted_as_numbers():
    assert _numbers("WI-BK-204 에 따라 3회 확인한다") == ["3"]
    assert _numbers("IMG_021") == []


def test_a_run_that_starts_with_a_digit_is_a_number_not_a_code():
    tokens = extract_tokens("구역 1A", "ko")
    assert [token.raw for token in tokens.numbers] == ["1"]
    assert tokens.others == ()


def test_text_without_tokens():
    tokens = extract_tokens("원료를 확인한다.", "ko")
    assert tokens.numbers == ()
    assert tokens.others == ()
