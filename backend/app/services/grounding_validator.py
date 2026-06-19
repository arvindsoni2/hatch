"""Entity-level grounding validator for tailored CVs.

Replaces the fuzzy-only check in CVTailor._validate_no_fabrication().
Provides deterministic blocking checks (company names, numbers, certifications,
clearance claims) plus advisory fuzzy similarity per bullet.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz

from ..schemas.tailor import TailoredCVResult

logger = logging.getLogger(__name__)

# Clearance/eligibility phrases that must exist verbatim in the master CV before
# they can appear in a tailored document.
_CLEARANCE_PATTERNS = re.compile(
    r"\b(sc[- ]cleared?|dv[- ]cleared?|security[- ]cleared?|"
    r"security clearance|nato clearance|developed vetting|strap)\b",
    re.IGNORECASE,
)

# Numeric/currency tokens: £3M, $500K, 99.9%, 2,000+, 10M+, 30% etc.
_NUMERIC_TOKEN_RE = re.compile(
    r"(?:[£$€¥][\d,]+(?:\.\d+)?(?:[KMBkm+]*)|"
    r"\d[\d,]*(?:\.\d+)?(?:[KMBkm%+]+))",
    re.IGNORECASE,
)

_FABRICATION_THRESHOLD = 70  # rapidfuzz score below this → advisory warning


def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace, strip combining diacritics."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_text).lower().strip()


def _in_source(value: str, source_norm: str) -> bool:
    """Return True if value appears as a substring of source_norm (normalised)."""
    if not value.strip():
        return True
    return _normalise(value) in source_norm


def _master_raw_text(master: dict[str, Any]) -> str:
    """Flatten master CV to a single normalised string for substring checks."""
    parts: list[str] = []

    # personal
    personal = master.get("personal", {})
    if isinstance(personal, dict):
        parts.extend(str(v) for v in personal.values() if v)

    # summary variants
    for v in (master.get("summary_variants") or {}).values():
        if isinstance(v, str):
            parts.append(v)

    # experience
    for exp in master.get("experience", []):
        if not isinstance(exp, dict):
            continue
        parts.extend([exp.get("role", ""), exp.get("company", ""), exp.get("period", "")])
        for ach in exp.get("achievements", []):
            parts.append(ach.get("text", "") if isinstance(ach, dict) else str(ach))

    # skills
    skills = master.get("skills", {})
    if isinstance(skills, dict):
        for grp in skills.values():
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))
    elif isinstance(skills, list):
        for grp in skills:
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))

    # certifications
    parts.extend(master.get("certifications", []))

    # education
    for edu in master.get("education", []):
        if isinstance(edu, str):
            parts.append(edu)
        elif isinstance(edu, dict):
            parts.extend(str(v) for v in edu.values() if isinstance(v, str))
            details = edu.get("details", [])
            if isinstance(details, list):
                parts.extend(str(item) for item in details if item)

    return _normalise(" ".join(str(p) for p in parts if p))


def _all_master_achievements(master: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for exp in master.get("experience", []):
        if not isinstance(exp, dict):
            continue
        for ach in exp.get("achievements", []):
            texts.append(ach.get("text", "") if isinstance(ach, dict) else str(ach))
    return texts


def validate(
    tailored: TailoredCVResult,
    master: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Run deterministic entity-level grounding checks plus fuzzy advisory pass.

    Blocking issues (returned first) must cause the document to be withheld.
    Advisory warnings (returned second) are logged but do not block.

    Args:
        tailored: The LLM-generated tailored CV.
        master: The confirmed master CV dict.

    Returns:
        (blocking, advisory) — two separate lists of human-readable strings.
    """
    from .master_cv_validator import _PLACEHOLDER_PATTERNS  # noqa: PLC0415

    blocking: list[str] = []
    advisory: list[str] = []

    source_norm = _master_raw_text(master)
    master_certs = [_normalise(c) for c in master.get("certifications", []) if isinstance(c, str)]

    def _has_ph(text: str) -> bool:
        return any(pat.search(text) for pat in _PLACEHOLDER_PATTERNS)

    # ── 1. Placeholder token checks (existing, blocking) ──────────────────────
    if _has_ph(tailored.summary):
        blocking.append(f"summary: contains placeholder text — {tailored.summary[:80]!r}")

    for idx, skill_group in enumerate(tailored.skills):
        for item in skill_group.get("items", []):
            if isinstance(item, str) and _has_ph(item):
                blocking.append(f"skills[{idx}].items: placeholder — {item!r}")

    for cert in tailored.certifications:
        if isinstance(cert, str) and _has_ph(cert):
            blocking.append(f"certifications: placeholder — {cert!r}")

    for exp in tailored.experience:
        if _has_ph(exp.role):
            blocking.append(f"experience.role: placeholder — {exp.role!r}")
        if _has_ph(exp.company):
            blocking.append(f"experience.company: placeholder — {exp.company!r}")

    for idx, edu in enumerate(tailored.education):
        for field_name in ("qualification", "institution", "year", "field", "location"):
            value = getattr(edu, field_name, "")
            if value and _has_ph(value):
                blocking.append(f"education[{idx}].{field_name}: placeholder — {value!r}")

    # ── 2. Company / role name verbatim check (blocking) ─────────────────────
    for exp in tailored.experience:
        if exp.company and not _in_source(exp.company, source_norm):
            blocking.append(
                f"experience.company: '{exp.company}' not found in master CV — "
                f"possible fabrication"
            )
        if exp.role and not _in_source(exp.role, source_norm):
            blocking.append(
                f"experience.role: '{exp.role}' not found in master CV — "
                f"possible fabrication"
            )

    # ── 3. Numeric/currency token check (blocking) ───────────────────────────
    for exp in tailored.experience:
        for achievement in exp.achievements:
            tokens = _NUMERIC_TOKEN_RE.findall(achievement)
            for tok in tokens:
                if not _in_source(tok, source_norm):
                    blocking.append(
                        f"achievement: numeric token '{tok}' not in master CV — "
                        f"fabricated metric in: {achievement[:60]!r}"
                    )

    # Also check summary for invented numbers
    for tok in _NUMERIC_TOKEN_RE.findall(tailored.summary):
        if not _in_source(tok, source_norm):
            blocking.append(
                f"summary: numeric token '{tok}' not in master CV — "
                f"fabricated metric: {tailored.summary[:80]!r}"
            )

    # ── 4. Certification verbatim check (blocking) ───────────────────────────
    for cert in tailored.certifications:
        if not isinstance(cert, str) or not cert.strip():
            continue
        if _has_ph(cert):
            continue  # already caught above
        if master_certs and _normalise(cert) not in master_certs:
            blocking.append(
                f"certifications: '{cert}' not in master CV certifications — possible fabrication"
            )

    # ── 4b. Education verbatim check (blocking) ─────────────────────────────
    for edu in tailored.education:
        for field_name in ("qualification", "institution", "year", "field", "location"):
            value = getattr(edu, field_name, "")
            if value and not _in_source(value, source_norm):
                blocking.append(
                    f"education.{field_name}: '{value}' not found in master CV — possible fabrication"
                )

    # ── 5. Clearance/eligibility claim check (blocking) ──────────────────────
    full_tailored_text = " ".join(
        [tailored.summary]
        + [a for exp in tailored.experience for a in exp.achievements]
    )
    for match in _CLEARANCE_PATTERNS.finditer(full_tailored_text):
        claim = match.group(0)
        if not _in_source(claim, source_norm):
            blocking.append(
                f"clearance claim: '{claim}' not in master CV — "
                f"cannot claim clearance not evidenced in the source"
            )

    # ── 6. Fuzzy advisory pass per bullet (advisory only) ────────────────────
    master_texts = _all_master_achievements(master)
    if master_texts:
        if len(tailored.summary) >= 30:
            best = max(
                (fuzz.partial_ratio(tailored.summary, mt) for mt in master_texts), default=0
            )
            if best < _FABRICATION_THRESHOLD:
                advisory.append(
                    f"Summary low similarity to master CV (score={best}) — "
                    f"verify no invented content: {tailored.summary[:80]!r}"
                )

        for exp in tailored.experience:
            for achievement in exp.achievements:
                if len(achievement) < 30:
                    continue
                best_score = max(
                    (fuzz.partial_ratio(achievement, mt) for mt in master_texts), default=0
                )
                if best_score < _FABRICATION_THRESHOLD:
                    advisory.append(
                        f"Possible fabrication (similarity={best_score}): {achievement[:80]!r}"
                    )

    return blocking, advisory
