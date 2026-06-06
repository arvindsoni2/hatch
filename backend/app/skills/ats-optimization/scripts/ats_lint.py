"""ATS lint — deterministic keyword coverage scorer.

Callable interface: ats_lint(cv_text: str, keywords: list[str]) -> float

Returns a score between 0.0 and 1.0 representing the fraction of keywords
found in the CV text using case-insensitive whole-word matching.
"""
from __future__ import annotations

import re


def ats_lint(cv_text: str, keywords: list[str]) -> float:
    """Score keyword coverage of cv_text against keywords.

    Args:
        cv_text: Plain text of the CV to score.
        keywords: List of ATS keywords to check for.

    Returns:
        Float in [0.0, 1.0] — fraction of keywords found.
    """
    if not keywords:
        return 1.0
    text_lower = cv_text.lower()
    found = sum(1 for kw in keywords if _kw_in_text(kw.lower(), text_lower))
    return found / len(keywords)


def _kw_in_text(keyword: str, text: str) -> bool:
    """Return True if keyword appears in text (case-insensitive, word-boundary aware)."""
    # Escape for regex and match at word boundaries
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text))
