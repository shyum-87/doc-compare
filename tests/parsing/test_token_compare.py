"""Comparing the tokens of a translated text with those of its source."""

from __future__ import annotations

from app.parsing.tokens import compare_tokens, extract_tokens


def _diff(translated, source, source_language):
    """The translation is always Korean."""
    return compare_tokens(extract_tokens(translated, "ko"), extract_tokens(source, source_language))


def test_the_same_tokens_match():
    diff = _diff("배합표 대비 ±1.0% 이내", "Within ±1.0% of the formula sheet", "en")
    assert diff.is_match
    assert (diff.missing, diff.extra) == ((), ())
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_the_order_does_not_matter():
    assert _diff("8℃ 이하, 2℃ 이상", "2℃ or above, 8℃ or below", "en").is_match


def test_a_vietnamese_decimal_comma_matches_by_value():
    assert _diff("±1.0% 이내", "Trong phạm vi ±1,0%", "vi").is_match
    assert _diff("1.5 kg", "1,5 kg", "vi").is_match


def test_a_vietnamese_thousands_dot_matches_by_value():
    assert _diff("1000 g", "1.000 g", "vi").is_match
    assert not _diff("1.000 g", "1.000 g", "vi").is_match  # one gram against a thousand


def test_an_english_thousands_comma_matches_by_value():
    assert _diff("1000 g", "1,000 g", "en").is_match
    assert _diff("1,000 g", "1,000 g", "en").is_match


def test_full_width_digits_match():
    assert _diff("180℃", "１８０℃", "zh").is_match


def test_a_changed_number_is_reported_from_both_sides():
    diff = _diff("±2.0% 이내", "Trong phạm vi ±1,0%", "vi")
    assert not diff.is_match
    assert diff.missing == ("num:1,0",)  # in the source, not in the translation
    assert diff.extra == ("num:2.0",)  # in the translation, not in the source
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_a_changed_unit_is_reported():
    diff = _diff("±1.0℃ 이내", "Within ±1.0%", "en")
    assert diff.missing == ("unit:%",)
    assert diff.extra == ("unit:°C",)


def test_a_dropped_sign_is_reported():
    assert _diff("18℃ 이하", "-18℃ or below", "en").missing == ("sym:neg",)
    assert _diff("1.0% 이내", "Within ±1.0%", "en").missing == ("sym:±",)
    assert _diff("2, 8℃", "2~8℃", "en").missing == ("sym:~",)


def test_a_changed_code_is_reported():
    diff = _diff("WI-BK-205 에 따른다", "Follow WI-BK-204", "en")
    assert diff.missing == ("code:WI-BK-204",)
    assert diff.extra == ("code:WI-BK-205",)


def test_tokens_are_counted():
    diff = _diff("2회, 2회, 3회", "2 times, 3 times", "en")
    assert diff.missing == ()
    assert diff.extra == ("num:2",)


def test_numbers_that_fit_neither_notation_are_compared_as_strings():
    diff = _diff("1.2.3 항", "Clause 1.2.3", "en")
    assert diff.is_match
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_a_number_that_fits_one_side_only_is_compared_as_a_string():
    assert _diff("1,5", "1,5", "en").is_match  # neither fits: same string
    assert _diff("1.5", "1.5", "vi").is_match  # fits Korean only: same string


def test_an_unmatched_number_that_does_not_fit_is_marked_ambiguous():
    diff = _diff("1.5 kg", "1,5 kg", "en")  # '1,5' is not English notation
    assert diff.missing == ("num:1,5",)
    assert diff.extra == ("num:1.5",)
    assert diff.ambiguous_source
    assert not diff.ambiguous_translated

    diff = _diff("1,5 kg", "1.5 kg", "en")
    assert diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_text_without_tokens_matches():
    assert _diff("원료를 확인한다.", "Check the raw material.", "en").is_match
