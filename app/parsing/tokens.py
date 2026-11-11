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

# NFKC leaves these two alone, so they are folded by hand: U+2212 minus, U+301C wave dash.
_FOLD = str.maketrans({"−": "-", "〜": "~"})

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[1-9][0-9]{0,2}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[1-9][0-9]{0,2}(?:\.[0-9]{3})+(?:,[0-9]+)?")

_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_ALNUM = _ASCII_LETTERS | _ASCII_DIGITS


def normalize(text: str) -> str:
    """NFKC (full-width -> half-width, '℃' -> '°C') plus the two hand-folded signs."""
    return unicodedata.normalize("NFKC", text).translate(_FOLD)


_UNITS_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted({normalize(unit) for unit in UNITS}, key=lambda unit: (-len(unit), unit))
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
    """Unit right after a number (zero or one space). Returns (unit, end position)."""
    start = position + 1 if text.startswith(" ", position) else position
    for unit in _UNITS_LONGEST_FIRST:
        if not text.startswith(unit, start):
            continue
        end = start + len(unit)
        if end < len(text) and _is_latin_letter(text[end]):
            continue  # '30 min': the 'm' is the start of a word, not a unit
        return unit, end
    return None


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
            if following in _ASCII_DIGITS and previous not in _ASCII_ALNUM:
                others.append("sym:neg")
            position += 1
        elif char in _ASCII_LETTERS:
            match = _CODE_RE.match(scanned, position)
            assert match is not None
            word = match.group().rstrip("-_")
            if any(letter in _ASCII_DIGITS for letter in word):
                others.append("code:" + word)
            position = match.end()
        elif char in _ASCII_DIGITS:
            match = _NUMBER_RE.match(scanned, position)
            assert match is not None
            raw = match.group()
            numbers.append(NumberToken(raw=raw, value=parse_number(raw, language)))
            position = match.end()
            unit = _unit_at(scanned, position)
            if unit is not None:
                others.append("unit:" + unit[0])
                position = unit[1]
        else:
            position += 1
    return Tokens(numbers=tuple(numbers), others=tuple(others))
