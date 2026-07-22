"""CV Parser — extracts structured MasterCV data from raw CV text using the primary LLM.

The parser is grounded by a post-parse verbatim check: every imported scalar
fact must appear as a substring of the raw CV text. Violations are cleared or
dropped and added to parse warnings.
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
from .prompt_catalog import prompt_contract_block

logger = logging.getLogger(__name__)

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
        render_prompt(
            "cv_parsing.j2",
            cv_text=text,
            prompt_contract=prompt_contract_block("cv_parsing"),
        )
    )

    try:
        raw: Any = await claude_client.complete_json(
            system_prompt, user_prompt, max_tokens=CV_PARSE.max_output
        )
    except Exception as exc:
        logger.error("CV parsing LLM call failed: %s", exc)
        # Return empty structure rather than crashing — user will see empty review form
        return CVParseResult(parsed=_empty_cv(), warnings=[f"LLM parse failed: {exc}"])

    if not isinstance(raw, dict):
        return CVParseResult(
            parsed=_empty_cv(),
            warnings=["Invalid top-level CV parse shape — expected an object"],
        )

    warnings: list[str] = []
    source_norm = _normalise(text)

    # ── Grounding checks ──────────────────────────────────────────────────────

    # personal fields — light check (just verify they're substrings if non-empty)
    personal = raw.get("personal")
    if not isinstance(personal, dict):
        personal = {}
    for field in (
        "full_name",
        "email",
        "phone",
        "location",
        "linkedin",
        "title",
    ):
        personal[field] = _ground_string(
            personal.get(field),
            source_norm,
            f"personal.{field}",
            warnings,
        )
    raw["personal"] = personal

    summaries = raw.get("summary_variants")
    if not isinstance(summaries, dict):
        summaries = {}
    for key, value in tuple(summaries.items()):
        summaries[key] = _ground_string(
            value,
            source_norm,
            f"summary_variants.{key}",
            warnings,
        )
    summaries.setdefault("default", "")
    raw["summary_variants"] = summaries

    # experience — company, role verbatim; numeric tokens in each achievement
    experience = raw.get("experience", [])
    if not isinstance(experience, list):
        experience = []
    cleaned_experience: list[dict[str, Any]] = []
    for exp_index, exp in enumerate(experience):
        if not isinstance(exp, dict):
            continue
        for field in ("company", "role", "period", "location"):
            if field in exp or field != "location":
                exp[field] = _ground_string(
                    exp.get(field),
                    source_norm,
                    f"experience.{exp_index}.{field}",
                    warnings,
                )

        clean_achievements: list[dict[str, str]] = []
        achievements = exp.get("achievements", [])
        if not isinstance(achievements, list):
            achievements = []
        for ach_index, ach in enumerate(achievements):
            ach_text = ach.get("text", "") if isinstance(ach, dict) else str(ach)
            grounded = _ground_string(
                ach_text,
                source_norm,
                f"experience.{exp_index}.achievements.{ach_index}",
                warnings,
            )
            if grounded:
                clean_achievements.append({"text": grounded})
        exp["achievements"] = clean_achievements
        cleaned_experience.append(exp)
    raw["experience"] = cleaned_experience

    # certifications — each string must appear verbatim
    certs: list[str] = []
    raw_certifications = raw.get("certifications", [])
    if not isinstance(raw_certifications, list):
        raw_certifications = []
    for cert in raw_certifications:
        if isinstance(cert, str) and cert.strip():
            if not _substring_present(cert, source_norm):
                warnings.append(
                    f"certifications: '{cert}' not found in source CV — dropped"
                )
            else:
                certs.append(cert)
    raw["certifications"] = certs

    skills_out: list[dict[str, Any]] = []
    raw_skills = raw.get("skills", [])
    if not isinstance(raw_skills, list):
        raw_skills = []
    for group_index, grp in enumerate(raw_skills):
        if isinstance(grp, dict):
            grp["category"] = _ground_string(
                grp.get("category"),
                source_norm,
                f"skills.{group_index}.category",
                warnings,
            )
            items = grp.get("items", [])
            if not isinstance(items, list):
                items = []
            grp["items"] = [
                grounded
                for item_index, item in enumerate(items)
                if (
                    grounded := _ground_string(
                        item,
                        source_norm,
                        f"skills.{group_index}.items.{item_index}",
                        warnings,
                    )
                )
            ]
            if grp["items"] or grp.get("category"):
                skills_out.append(grp)
    raw["skills"] = skills_out

    education_out: list[dict[str, str]] = []
    raw_education = raw.get("education", [])
    if not isinstance(raw_education, list):
        raw_education = []
    for education_index, education in enumerate(raw_education):
        if not isinstance(education, dict):
            continue
        education_out.append(
            {
                field: _ground_string(
                    education.get(field),
                    source_norm,
                    f"education.{education_index}.{field}",
                    warnings,
                )
                for field in ("qualification", "institution", "year")
            }
        )
    raw["education"] = education_out

    return CVParseResult(parsed=raw, warnings=warnings)


def _ground_string(
    value: Any,
    source_norm: str,
    path: str,
    warnings: list[str],
) -> str:
    """Keep a scalar only when it is present verbatim in source evidence."""
    if not isinstance(value, str) or not value.strip():
        return ""
    if _substring_present(value, source_norm):
        return value
    warnings.append(f"{path}: '{value}' not found in source CV — cleared")
    return ""


def _empty_cv() -> dict[str, Any]:
    return {
        "personal": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "title": ""},
        "summary_variants": {"default": ""},
        "experience": [],
        "skills": [],
        "certifications": [],
        "education": [],
    }
