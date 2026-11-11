"""Number notation by language (spec section 6.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsing.tokens import parse_number


@pytest.mark.parametrize(
    "raw, language, value",
    [
        # ko / en / zh: '.' is the decimal point, ',' groups thousands
        ("180", "ko", "180"),
        ("1.5", "ko", "1.5"),
        ("1.0", "en", "1.0"),
        ("0.1", "ko", "0.1"),
        ("1,000", "en", "1000"),
        ("1,000", "ko", "1000"),
        ("1,000", "zh", "1000"),
        ("123,456", "en", "123456"),
        ("10,000,000", "en", "10000000"),
        ("1,000.5", "en", "1000.5"),
        ("1,000.1", "en", "1000.1"),
        ("1.000", "en", "1.000"),  # one, written with three decimals
        # vi: ',' is the decimal point, '.' groups thousands
        ("180", "vi", "180"),
        ("1,5", "vi", "1.5"),
        ("1,0", "vi", "1.0"),
        ("0,5", "vi", "0.5"),
        ("0,1", "vi", "0.1"),
        ("0,125", "vi", "0.125"),
        ("1.000", "vi", "1000"),
        ("123.456", "vi", "123456"),
        ("1.234.567", "vi", "1234567"),
        ("1.000,25", "vi", "1000.25"),
        ("1.000,1", "vi", "1000.1"),
        ("1,000", "vi", "1.000"),  # one, written with three decimals
    ],
)
def test_numbers_that_fit_the_notation(raw, language, value):
    assert parse_number(raw, language) == Decimal(value)


@pytest.mark.parametrize(
    "raw, language",
    [
        ("1,5", "en"),  # a comma, but not three digits after it
        ("12,34", "ko"),
        ("1,00", "zh"),
        ("1.2.3", "ko"),
        ("1,000,5", "en"),
        ("1.5", "vi"),  # a dot, but not three digits after it
        ("12.34", "vi"),
        ("1,000.5", "vi"),
        ("10,000,000", "vi"),
        ("", "ko"),
        ("", "vi"),
        ("abc", "ko"),
        # a grouped number does not start with 0
        ("0,125", "en"),
        ("01,234", "ko"),
        ("0.500", "vi"),
        ("00.123", "vi"),
        # one to three digits before the first separator, exactly three after each
        ("1234,567", "en"),
        ("1,0000", "en"),
        (",123", "en"),
        ("1234.567", "vi"),
        ("1.0000", "vi"),
        (".123", "vi"),
        # the decimal mark comes once, after the groups, with digits on both sides
        ("1.000.000", "en"),
        ("1,000.5.5", "en"),
        ("1,000.", "en"),
        ("5.", "ko"),
        (".5", "ko"),
        ("1.000.5", "vi"),
        ("1.000,5,5", "vi"),
        ("1.000,", "vi"),
        ("5,", "vi"),
        (",5", "vi"),
        # nothing but the digits 0-9 and the two separators
        ("-5", "ko"),
        ("+5", "ko"),
        (" 5", "ko"),
        ("5\n", "ko"),
        ("5\n", "vi"),
        ("1,000\n", "en"),
        ("1.000\n", "vi"),
        ("1e3", "en"),
        ("1_000", "en"),
        ("\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT TWO}", "ko"),
        ("\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT TWO}", "vi"),
        ("1.\N{FULLWIDTH DIGIT FIVE}", "ko"),
        ("1,\N{FULLWIDTH DIGIT FIVE}", "vi"),
        ("1,00\N{FULLWIDTH DIGIT ZERO}", "en"),
        ("1.00\N{FULLWIDTH DIGIT ZERO}", "vi"),
        ("1,000.\N{FULLWIDTH DIGIT FIVE}", "en"),
        ("1.000,\N{FULLWIDTH DIGIT FIVE}", "vi"),
        ("\N{ARABIC-INDIC DIGIT ONE}\N{ARABIC-INDIC DIGIT TWO}", "en"),
    ],
)
def test_numbers_that_do_not_fit_the_notation(raw, language):
    assert parse_number(raw, language) is None


def test_the_same_digits_mean_different_values():
    assert parse_number("1.000", "vi") == 1000
    assert parse_number("1.000", "en") == 1
    assert parse_number("1,000", "en") == 1000
    assert parse_number("1,000", "vi") == 1


def test_values_compare_by_amount_not_by_spelling():
    assert parse_number("1,0", "vi") == parse_number("1.0", "ko")
    assert parse_number("1.50", "ko") == parse_number("1,5", "vi")


def test_a_value_is_an_exact_decimal():
    for raw, language in [("0.1", "ko"), ("1,000.1", "en"), ("0,1", "vi"), ("1.000,1", "vi")]:
        assert isinstance(parse_number(raw, language), Decimal)
    assert parse_number("0.1", "ko") + parse_number("0,2", "vi") == Decimal("0.3")
