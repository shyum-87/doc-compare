"""Paths of the sample documents. Everything under tests/fixtures is synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ko_sample() -> Path:
    """Korean sample: a baseline document, and also the translation of the three below."""
    return FIXTURES / "rag_ko" / "sample_bakery_sop.md"


@pytest.fixture(scope="session")
def source_samples() -> dict[str, Path]:
    """The same sample before translation, by original language."""
    return {
        language: FIXTURES / "rag" / f"sample_bakery_sop.{language}.md"
        for language in ("en", "vi", "zh")
    }
