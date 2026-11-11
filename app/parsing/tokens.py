"""Tokens compared between a translation and its source: numbers, units, symbols, codes.

Only these tokens are compared, by count and without regard to order. The stored text
is never changed; normalization happens only on the copy that is scanned here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.models.document import Language

# One place for the unit table. Add units here when real documents show more.
UNITS: tuple[str, ...] = (
    "℃", "°C", "℉", "%", "μm", "mm", "cm", "m", "mg", "g", "kg",
    "mL", "L", "Pa", "kPa", "MPa", "rpm", "ppm",
)  # fmt: skip

# Other ways of writing a unit of the table. NFKC turns '㎖' into 'ml' and 'ℓ' into 'l'.
UNIT_SPELLINGS: dict[str, str] = {"ml": "mL", "l": "L"}

# NFKC leaves these alone, so they are folded by hand. The em dash is left as it is:
# Chinese writes it twice as a punctuation mark.
_FOLD = str.maketrans(
    {
        "\N{HYPHEN}": "-",  # NFKC turns the non-breaking hyphen U+2011 into this one
        "\N{FIGURE DASH}": "-",
        "\N{EN DASH}": "-",
        "\N{MINUS SIGN}": "-",
        "\N{WAVE DASH}": "~",
        "\N{TILDE OPERATOR}": "~",
    }
)

# NFKC turns a superscript into a plain character, so '10³' would read as 103 and the '⁻'
# of 'm⁻³' as a hyphen inside a word. Two kinds are marked: a superscript right after a
# digit, and a superscript sign right before a superscript digit. The '²' of 'cm²' stays
# with its letters, as in 'cm2'.
_SUPERSCRIPT_TO_MARK = re.compile(
    "(?<=[0-9\N{FULLWIDTH DIGIT ZERO}-\N{FULLWIDTH DIGIT NINE}])[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]|[⁺⁻](?=[⁰¹²³⁴⁵⁶⁷⁸⁹])"
)

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[1-9][0-9]{0,2}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[1-9][0-9]{0,2}(?:\.[0-9]{3})+(?:,[0-9]+)?")

_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
# After a code: the next word is a code of its own (a run that holds a digit).
_NEXT_CODE_RE = re.compile(r" [A-Za-z][A-Za-z_-]*[0-9]")
# After letters: a negative exponent as normalize() writes it ('m⁻²' -> 'm^-2').
_NEGATIVE_EXPONENT_RE = re.compile(r"\^-[0-9]+")
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_ALNUM = _ASCII_LETTERS | _ASCII_DIGITS


def normalize(text: str) -> str:
    """NFKC (full-width -> half-width, '℃' -> '°C') plus the hand-folded signs.

    A '^' goes first before a superscript right after a digit and before a superscript
    sign right before a superscript digit: '10³' -> '10^3', '10⁻³' -> '10^-3',
    'm⁻³' -> 'm^-3'.
    """
    marked = _SUPERSCRIPT_TO_MARK.sub(r"^\g<0>", text)
    return unicodedata.normalize("NFKC", marked).translate(_FOLD)


_UNIT_BY_SPELLING: dict[str, str] = {normalize(unit): normalize(unit) for unit in UNITS}
_UNIT_BY_SPELLING.update(UNIT_SPELLINGS)
_SPELLINGS_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted(_UNIT_BY_SPELLING, key=lambda spelling: (-len(spelling), spelling))
)


def parse_number(raw: str, language: Language) -> Optional[Decimal]:
    """Value of `raw` in the notation of `language`, or None if it does not fit.

    ko/en/zh: '.' decimal, ',' thousands. vi: ',' decimal, '.' thousands.
    A thousands separator counts only when exactly three digits follow it. A grouped
    number starts with one to three digits, and the first of them is not 0.
    """
    if language == "vi":
        if _PLAIN_COMMA.fullmatch(raw):
            return Decimal(raw.replace(",", "."))
        if _GROUPED_COMMA.fullmatch(raw):
            return Decimal(raw.replace(".", "").replace(",", "."))
        return None
    if _PLAIN_DOT.fullmatch(raw):
        return Decimal(raw)
    if _GROUPED_DOT.fullmatch(raw):
        return Decimal(raw.replace(",", ""))
    return None


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: Optional[Decimal]


@dataclass(frozen=True)
class Tokens:
    numbers: tuple[NumberToken, ...]
    others: tuple[str, ...]  # 'unit:°C', 'sym:±', 'sym:~', 'sym:neg', 'code:BK01'


def _is_latin_letter(char: str) -> bool:
    return char.isalpha() and "LATIN" in unicodedata.name(char, "")


def _unit_at(text: str, position: int) -> Optional[tuple[str, int]]:
    """Unit right after a digit (zero or one space). Returns (unit, end position)."""
    start = position + 1 if text.startswith(" ", position) else position
    for spelling in _SPELLINGS_LONGEST_FIRST:
        if not text.startswith(spelling, start):
            continue
        end = start + len(spelling)
        if end < len(text) and _is_latin_letter(text[end]):
            continue  # '30 min': the 'm' is the start of a word, not a unit
        return _UNIT_BY_SPELLING[spelling], end
    return None


def _leading_point_at(text: str, position: int) -> bool:
    """'.5': a '.' right before a digit, and not after a letter or a digit ('No.5')."""
    return (
        text.startswith(".", position)
        and text[position + 1 : position + 2] in _ASCII_DIGITS
        and not text[position - 1 : position].isalnum()
    )


def extract_tokens(text: str, language: Language) -> Tokens:
    scanned = normalize(text)
    numbers: list[NumberToken] = []
    others: list[str] = []
    position = 0
    while position < len(scanned):
        char = scanned[position]
        if char in "±~":
            others.append("sym:" + char)
            position += 1
        elif char == "-":
            following = scanned[position + 1 : position + 2]
            previous = scanned[position - 1 : position]
            before_number = following in _ASCII_DIGITS or _leading_point_at(scanned, position + 1)
            if before_number and previous not in _ASCII_ALNUM:
                others.append("sym:neg")
            position += 1
        elif char in _ASCII_LETTERS:
            match = _CODE_RE.match(scanned, position)
            assert match is not None
            word = match.group().rstrip("-_")
            if any(letter in _ASCII_DIGITS for letter in word):
                others.append("code:" + word)
            else:
                # 'kg·m⁻²': the letters before a negative exponent stay, as in 'm-2'. The
                # sign and the number of the exponent are still read after this.
                exponent = _NEGATIVE_EXPONENT_RE.match(scanned, match.end())
                if exponent is not None:
                    others.append("code:" + word + exponent.group()[1:])
            position = match.end()
            ends_in_digit = scanned[position - 1] in _ASCII_DIGITS
            if ends_in_digit and not _NEXT_CODE_RE.match(scanned, position):
                # 'A-5 kg': a unit is read after a code that ends in a digit too, unless
                # the next word is a code of its own ('A1 L2', 'T1 L-204A')
                unit = _unit_at(scanned, position)
                if unit is not None:
                    others.append("unit:" + unit[0])
                    position = unit[1]
        elif char in _ASCII_DIGITS or _leading_point_at(scanned, position):
            # '.5' keeps its point: it fits no notation, so it is compared as written
            match = _NUMBER_RE.match(scanned, position + 1 if char == "." else position)
            assert match is not None
            raw = scanned[position : match.end()]
            numbers.append(NumberToken(raw=raw, value=parse_number(raw, language)))
            position = match.end()
            unit = _unit_at(scanned, position)
            if unit is not None:
                others.append("unit:" + unit[0])
                position = unit[1]
        else:
            position += 1
    return Tokens(numbers=tuple(numbers), others=tuple(others))
