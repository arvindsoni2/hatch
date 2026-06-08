"""T12: select_tone_variant sector mapping."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.cl_generator import select_tone_variant


def _jd(sector: str | None):
    jd = MagicMock()
    jd.sector = sector
    return jd


@pytest.mark.parametrize("sector,expected", [
    # Formal sectors → A
    ("construction", "A"),
    ("Construction", "A"),
    ("finance", "A"),
    ("government", "A"),
    ("energy", "A"),
    ("defence", "A"),
    ("defense", "A"),
    ("banking", "A"),
    ("infrastructure", "A"),
    ("public sector", "A"),
    # Conversational sectors → B
    ("technology", "B"),
    ("tech", "B"),
    ("startup", "B"),
    ("creative", "B"),
    ("saas", "B"),
    ("gaming", "B"),
    # Unknown / missing → A
    (None, "A"),
    ("", "A"),
    ("retail", "A"),
    ("healthcare", "A"),
])
def test_select_tone_variant(sector, expected):
    assert select_tone_variant(_jd(sector)) == expected


def test_select_tone_variant_partial_match_tech():
    """'financial technology' contains 'technology' → B."""
    assert select_tone_variant(_jd("financial technology")) == "B"


def test_select_tone_variant_partial_match_construction():
    """'construction management' → A."""
    assert select_tone_variant(_jd("construction management")) == "A"
