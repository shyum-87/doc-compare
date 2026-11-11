"""Tokens compared between a translation and its source: numbers, units, symbols, codes.

Only these tokens are compared, by count and without regard to order. The stored text
is never changed; normalization happens only on the copy that is scanned here.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from app.models.document import Language

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]+)?")


def parse_number(raw: str, language: Language) -> Optional[Decimal]:
    """Value of `raw` in the notation of `language`, or None if it does not fit.

    ko/en/zh: '.' decimal, ',' thousands. vi: ',' decimal, '.' thousands.
    A thousands separator counts only when exactly three digits follow it.
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
