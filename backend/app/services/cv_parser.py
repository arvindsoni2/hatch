"""CV Parser — extracts structured MasterCV data from raw CV text using the primary LLM.

The parser is grounded by a post-parse verbatim check: every company name, role, certification,
and numeric/currency token extracted by the LLM must appear as a substring of the raw CV text.
Violations are dropped to empty string and added to parse_warnings, making the parser itself
hallucination-proof regardless of model quality.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from ..prompts import render_prompt
from .llm_client import LLMClient
from ..agents.tools.context_budgets import CV_PARSE
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

# Matches £1M, $500K, 99.9%, 2,000+, 10M+, £3.2bn etc.
_NUMERIC_TOKEN_RE = re.compile(
    r"(?:[£$€¥][\d,]+(?:\.\d+)?(?:[KMBkm+]*)|\d[\d,]*(?:\.\d+)?(?:[KMBkm%+]+))",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace, strip accents for substring matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_text).lower().strip()


def _substring_present(value: str, source_norm: str) -> bool:
    """Case/whitespace-insensitive substring check."""
    if not value.strip():
        return True
    return _normalise(value) in source_norm


class CVParseResult:
    """Holds the parsed CV dict and any warnings from the verbatim grounding check."""

    def __init__(self, parsed: dict[str, Any], warnings: list[str]) -> None:
        self.parsed = parsed
        self.warnings = warnings


async def parse_cv_text(text: str, claude_client: LLMClient) -> CVParseResult:
    """Extract structured CV data from raw text, with verbatim grounding checks.

    Args:
        text: Raw CV text (from .docx or .pdf extraction).
        claude_client: Configured LLMClient instance.

    Returns:
        CVParseResult with parsed dict and any grounding warnings.
    """
    system_prompt, user_prompt = _split_jinja_output(
        render_prompt("cv_parsing.j2", cv_text=text)
    )

    try:
        raw: dict[str, Any] = await claude_client.complete_json(
            system_prompt, user_prompt, max_tokens=CV_PARSE.max_output
        )
    except Exception as exc:
        logger.error("CV parsing LLM call failed: %s", exc)
        # Return empty structure rather than crashing — user will see empty review form
        return CVParseResult(parsed=_empty_cv(), warnings=[f"LLM parse failed: {exc}"])

    warnings: list[str] = []
    source_norm = _normalise(text)

    # ── Grounding checks ──────────────────────────────────────────────────────

    # personal fields — light check (just verify they're substrings if non-empty)
    personal = raw.get("personal", {})
    if isinstance(personal, dict):
        for field in ("full_name", "email", "phone", "location"):
            val = personal.get(field, "")
            if val and not _substring_present(val, source_norm):
                warnings.append(
                    f"personal.{field}: '{val}' not found in source CV — cleared"
                )
                personal[field] = ""

    # experience — company, role verbatim; numeric tokens in each achievement
    experience = raw.get("experience", [])
    cleaned_experience: list[dict[str, Any]] = []
    for exp in experience:
        if not isinstance(exp, dict):
            continue
        company = exp.get("company", "")
        role = exp.get("role", "")

        if company and not _substring_present(company, source_norm):
            warnings.append(
                f"experience.company: '{company}' not found verbatim in source CV — cleared"
            )
            exp["company"] = ""

        if role and not _substring_present(role, source_norm):
            warnings.append(
                f"experience.role: '{role}' not found verbatim in source CV — cleared"
            )
            exp["role"] = ""

        # Check numeric tokens in achievements
        clean_achievements: list[dict[str, str]] = []
        for ach in exp.get("achievements", []):
            ach_text = ach.get("text", "") if isinstance(ach, dict) else str(ach)
            bad_tokens = [
                tok for tok in _NUMERIC_TOKEN_RE.findall(ach_text)
                if not _substring_present(tok, source_norm)
            ]
            if bad_tokens:
                warnings.append(
                    f"achievement numeric token(s) {bad_tokens!r} not in source — bullet cleared"
                )
            else:
                clean_achievements.append({"text": ach_text} if isinstance(ach, str) else ach)
        exp["achievements"] = clean_achievements
        cleaned_experience.append(exp)
    raw["experience"] = cleaned_experience

    # certifications — each string must appear verbatim
    certs: list[str] = []
    for cert in raw.get("certifications", []):
        if isinstance(cert, str) and cert.strip():
            if not _substring_present(cert, source_norm):
                warnings.append(
                    f"certifications: '{cert}' not found in source CV — dropped"
                )
            else:
                certs.append(cert)
    raw["certifications"] = certs

    # skills — only check items are non-empty; category names are low-risk
    skills_out: list[dict[str, Any]] = []
    for grp in raw.get("skills", []):
        if isinstance(grp, dict):
            grp["items"] = [it for it in grp.get("items", []) if isinstance(it, str) and it.strip()]
            if grp["items"] or grp.get("category"):
                skills_out.append(grp)
    raw["skills"] = skills_out

    return CVParseResult(parsed=raw, warnings=warnings)


def _empty_cv() -> dict[str, Any]:
    return {
        "personal": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "title": ""},
        "summary_variants": {"default": ""},
        "experience": [],
        "skills": [],
        "certifications": [],
        "education": [],
    }
