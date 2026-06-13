"""Pre-flight validation and markup normalisation for master_cv.json.

validate_master_cv  — returns field-level error strings for placeholder tokens
                      that would propagate verbatim into generated documents.
normalise_master_cv — returns a deep-copy with LaTeX/markdown artefacts
                      replaced by plain text equivalents.
MasterCVError       — raised by CVTailor.tailor() when validation finds blockers.
"""
from __future__ import annotations

import copy
import re
from typing import Any


# ---------------------------------------------------------------------------
# Sentinel patterns — values that indicate an unfilled template field
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE),
    re.compile(r"\bXXXX\b"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"your\.email", re.IGNORECASE),
    re.compile(r"your-profile", re.IGNORECASE),
    re.compile(r"\[\.{3}\]"),                  # [...]
    re.compile(r"\[Company Name\]", re.IGNORECASE),
]

_LATEX_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\textsterling\b"), "£"),
    (re.compile(r"\\\$"), "$"),
    (re.compile(r"\\\&"), "&"),
    (re.compile(r"\$[^$]+\$"), ""),           # strip $...$ math mode
    (re.compile(r"\*{2,}"), ""),              # trim stray **
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class MasterCVError(ValueError):
    """Raised when the master CV contains placeholder tokens that would corrupt output."""


def validate_master_cv(cv: dict[str, Any]) -> list[str]:
    """Scan a master CV dict for placeholder tokens.

    Args:
        cv: Parsed master CV (the full dict from master_cv.json).

    Returns:
        List of human-readable error strings, one per offending field.
        Empty list means the CV is clean.
    """
    errors: list[str] = []

    # Personal block
    personal = cv.get("personal", {})
    for field, value in personal.items():
        if isinstance(value, str) and _has_placeholder(value):
            errors.append(f"personal.{field}: contains placeholder value — {value!r}")

    # Summary variants
    for key, text in cv.get("summary_variants", {}).items():
        if isinstance(text, str) and _has_placeholder(text):
            errors.append(f"summary_variants.{key}: contains placeholder text")

    # Experience headers and achievements
    for idx, exp in enumerate(cv.get("experience", [])):
        if not isinstance(exp, dict):
            continue
        company = exp.get("company", "")
        if isinstance(company, str) and _has_placeholder(company):
            errors.append(f"experience[{idx}].company: placeholder company name — {company!r}")
        role = exp.get("role", "")
        if isinstance(role, str) and _has_placeholder(role):
            errors.append(f"experience[{idx}].role: placeholder role — {role!r}")
        for aidx, ach in enumerate(exp.get("achievements", [])):
            text = ach.get("text", "") if isinstance(ach, dict) else str(ach)
            if _has_placeholder(text):
                errors.append(f"experience[{idx}].achievements[{aidx}]: placeholder text")

    return errors


def normalise_master_cv(cv: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of cv with LaTeX/markup artefacts replaced.

    Substitutions applied recursively to all string values:
      \\textsterling → £
      \\$            → $ (literal dollar, not math mode)
      \\&            → &
      $...$          → '' (strip math mode entirely)
      stray **       → '' (strip bold markers)

    The original dict is never mutated.
    """
    return _walk(copy.deepcopy(cv))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _has_placeholder(text: str) -> bool:
    return any(pat.search(text) for pat in _PLACEHOLDER_PATTERNS)


def _clean(text: str) -> str:
    for pattern, replacement in _LATEX_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return text


def _walk(obj: Any) -> Any:
    if isinstance(obj, str):
        return _clean(obj)
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    return obj
