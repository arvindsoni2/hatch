"""Shared evidence, prompt, provenance, and validation contracts for writing tasks."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

EVIDENCE_SCHEMA_VERSION = "1.0.0"
VALIDATION_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class PromptMetadata:
    prompt_id: str
    prompt_version: str
    schema_version: str
    task_name: str


@dataclass(frozen=True)
class NumericToken:
    raw: str
    normalized: str
    context: str


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    text: str
    source_path: str
    immutable_tokens: tuple[str, ...]
    semantic_anchors: tuple[str, ...]
    evidence_type: str


@dataclass(frozen=True)
class ValidationIssue:
    gate: str
    code: str
    severity: Literal["blocking", "advisory"]
    message: str
    expected: str | None = None
    observed: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: tuple[ValidationIssue, ...]
    metrics: dict[str, int | float | str]


@dataclass(frozen=True)
class ClaimProvenance:
    text: str
    source_evidence_ids: tuple[str, ...]
    change_type: Literal["preserved", "rephrased", "removed"]
    new_claims: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationProvenance:
    prompt_metadata: PromptMetadata
    evidence_schema_version: str
    source_evidence_ids: tuple[str, ...]
    validation: ValidationResult
    claims: tuple[ClaimProvenance, ...] = ()
    content_plan: dict[str, list[str]] | None = None
    workflow: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CV_TAILORING_PROMPT = PromptMetadata(
    prompt_id="cv_tailoring",
    prompt_version="2.0.0",
    schema_version="1.0.0",
    task_name="cv_tailoring",
)
COVER_LETTER_GENERATION_PROMPT = PromptMetadata(
    prompt_id="cover_letter_generation",
    prompt_version="2.0.0",
    schema_version="1.0.0",
    task_name="cover_letter_generation",
)
COVER_LETTER_REPAIR_PROMPT = PromptMetadata(
    prompt_id="cover_letter_repair",
    prompt_version="1.0.0",
    schema_version="1.0.0",
    task_name="cover_letter_repair",
)
COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT = PromptMetadata(
    prompt_id="cover_letter_paragraph_regeneration",
    prompt_version="1.0.0",
    schema_version="1.0.0",
    task_name="cover_letter_paragraph_regeneration",
)
SHARED_FACTUALITY_PROMPT = PromptMetadata(
    prompt_id="shared_factuality_contract",
    prompt_version="1.0.0",
    schema_version="1.0.0",
    task_name="shared_factuality",
)
SHARED_NUMERIC_FIDELITY_PROMPT = PromptMetadata(
    prompt_id="shared_numeric_fidelity_contract",
    prompt_version="1.0.0",
    schema_version="1.0.0",
    task_name="shared_numeric_fidelity",
)

SHARED_FACTUALITY_CONTRACT = """SHARED FACTUALITY CONTRACT (v1.0.0):
- Use APPROVED_EVIDENCE only for candidate claims.
- You may preserve or rephrase evidence, but must not invent facts or infer missing details.
- If evidence is insufficient, omit the claim or use neutral wording.
- Do not invent examples, employers, skills, certifications, outcomes, team sizes, budgets, durations, or metrics."""

SHARED_NUMERIC_FIDELITY_CONTRACT = """SHARED NUMERIC-FIDELITY CONTRACT (v1.0.0):
- Preserve every IMMUTABLE_TOKEN exactly when using its associated evidence.
- Do not calculate, combine, estimate, extrapolate, round, or infer numeric claims.
- Do not add a number that is absent from APPROVED_EVIDENCE.
- Preserve signs, plus signs, percentages, currency symbols, decimals, commas, ranges, dashes, and units exactly."""

FINAL_COMPLIANCE_REMINDER = """FINAL CHECK BEFORE RETURNING:
1. Use only APPROVED_EVIDENCE for candidate claims.
2. Preserve every IMMUTABLE_TOKEN exactly.
3. Return only the required structured schema."""


def prompt_metadata_records() -> dict[str, dict[str, str]]:
    """Return stable JSON-ready metadata for all PR2 writing contracts."""
    values = (
        CV_TAILORING_PROMPT,
        COVER_LETTER_GENERATION_PROMPT,
        COVER_LETTER_REPAIR_PROMPT,
        COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
        SHARED_FACTUALITY_PROMPT,
        SHARED_NUMERIC_FIDELITY_PROMPT,
    )
    return {item.prompt_id: asdict(item) for item in values}


def evidence_records(ledger: Iterable[EvidenceItem]) -> list[dict[str, Any]]:
    """Serialize approved evidence for deterministic prompt assembly."""
    return [asdict(item) for item in ledger]


def normalize_evidence_text(text: str) -> str:
    """Normalize evidence deterministically without changing meaningful symbols."""
    normalized = unicodedata.normalize(
        "NFC",
        str(text).replace("\r\n", "\n").replace("\r", "\n"),
    )
    return re.sub(r"\s+", " ", normalized).strip()


def stable_evidence_id(source_path: str, text: str) -> str:
    """Derive the versioned stable ID required by the evidence contract."""
    canonical = "\n".join(
        (
            EVIDENCE_SCHEMA_VERSION,
            source_path,
            normalize_evidence_text(text),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


_NUMERIC_UNIT = (
    r"(?:budgets?|years?|months?|weeks?|days?|hours?|locations?|sites?|users?|"
    r"people|employees?|members?|projects?|programmes?|programs?|teams?|countries|"
    r"regions?|clients?|customers?|systems?|applications?|services?|records?|"
    r"transactions?|requests?)"
)
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMERIC_TOKEN_RE = re.compile(
    rf"""
    (?<![\w@])
    (?:
        [£$€¥]\s?{_NUMBER}(?:[kmbKMB]|(?:\s+(?:million|billion|thousand)))?
            (?:\s+{_NUMERIC_UNIT})?
      | [+-]?{_NUMBER}\s*%(?!\w)
      | [+-]?{_NUMBER}\s*\+(?:\s+{_NUMERIC_UNIT})?
      | [+-]?{_NUMBER}(?:\s*[–—-]\s*[+-]?{_NUMBER})(?:\s+{_NUMERIC_UNIT})?
      | [+-]?{_NUMBER}(?:\s+{_NUMERIC_UNIT})
      | [+-]?{_NUMBER}
    )
    (?![\w@])
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NON_PROSE_TOKEN_RE = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|<[^>]+>",
    re.IGNORECASE,
)


def extract_numeric_tokens(text: str) -> tuple[NumericToken, ...]:
    """Extract immutable numeric expressions from prose in source order."""
    normalized_text = normalize_evidence_text(
        _NON_PROSE_TOKEN_RE.sub(" ", str(text))
    )
    tokens: list[NumericToken] = []
    for match in _NUMERIC_TOKEN_RE.finditer(normalized_text):
        raw = re.sub(r"\s*([–—-])\s*", r"\1", match.group(0)).strip()
        tokens.append(
            NumericToken(
                raw=raw,
                normalized=normalize_evidence_text(raw).casefold(),
                context=normalized_text,
            )
        )
    return tuple(tokens)


def _evidence_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "name", "title", "qualification"):
            candidate = value.get(key)
            if candidate:
                return str(candidate)
        return ""
    return str(value) if value is not None else ""


def build_evidence_ledger(master: dict[str, Any]) -> tuple[EvidenceItem, ...]:
    """Build an ordered, deduplicated ledger from master or tailored CV data."""
    items: list[EvidenceItem] = []
    seen_text: set[str] = set()

    def add(source_path: str, value: Any, evidence_type: str) -> None:
        text = normalize_evidence_text(_evidence_text(value))
        if not text or text in seen_text:
            return
        seen_text.add(text)
        items.append(
            EvidenceItem(
                id=stable_evidence_id(source_path, text),
                text=text,
                source_path=source_path,
                immutable_tokens=tuple(
                    token.raw for token in extract_numeric_tokens(text)
                ),
                semantic_anchors=(),
                evidence_type=evidence_type,
            )
        )

    summary = master.get("summary")
    if summary:
        add("summary", summary, "profile_summary")
    variants = master.get("summary_variants", {})
    if isinstance(variants, dict):
        for key, value in variants.items():
            add(f"summary_variants.{key}", value, "profile_summary")

    for exp_index, experience in enumerate(master.get("experience", [])):
        if not isinstance(experience, dict):
            continue
        for field in ("responsibilities", "achievements"):
            values = experience.get(field, [])
            if not isinstance(values, list):
                continue
            evidence_type = (
                "role_responsibility" if field == "responsibilities" else "achievement"
            )
            for item_index, value in enumerate(values):
                add(
                    f"experience.{exp_index}.{field}.{item_index}",
                    value,
                    evidence_type,
                )

    raw_skills = master.get("skills", {})
    skill_groups = (
        raw_skills.items()
        if isinstance(raw_skills, dict)
        else enumerate(raw_skills)
        if isinstance(raw_skills, list)
        else ()
    )
    for group_key, group in skill_groups:
        if not isinstance(group, dict):
            continue
        for item_index, value in enumerate(group.get("items", [])):
            add(f"skills.{group_key}.items.{item_index}", value, "skill")

    for item_index, education in enumerate(master.get("education", [])):
        if isinstance(education, dict):
            for field in (
                "qualification",
                "degree",
                "award",
                "field",
                "institution",
                "details",
            ):
                value = education.get(field)
                if isinstance(value, list):
                    for detail_index, detail in enumerate(value):
                        add(
                            f"education.{item_index}.{field}.{detail_index}",
                            detail,
                            "education",
                        )
                elif value:
                    add(f"education.{item_index}.{field}", value, "education")
        else:
            add(f"education.{item_index}", education, "education")

    for item_index, certification in enumerate(master.get("certifications", [])):
        add(f"certifications.{item_index}", certification, "certification")

    personal = master.get("personal", {})
    if isinstance(personal, dict):
        for field, value in personal.items():
            add(f"personal.{field}", value, "profile")

    for field, evidence_type in (
        ("preferences", "preference"),
        ("eligibility", "eligibility"),
    ):
        value = master.get(field)
        if isinstance(value, dict):
            for key, entry in value.items():
                add(f"{field}.{key}", entry, evidence_type)
        elif isinstance(value, list):
            for item_index, entry in enumerate(value):
                add(f"{field}.{item_index}", entry, evidence_type)
        elif value:
            add(field, value, evidence_type)

    return tuple(items)


def validate_numeric_fidelity(
    candidate_prose: Iterable[str],
    ledger: Iterable[EvidenceItem],
    allowed_context_prose: Iterable[str] = (),
) -> ValidationResult:
    """Block numeric prose absent from candidate evidence or declared context."""
    evidence = tuple(ledger)
    allowed = {
        normalize_evidence_text(token).casefold()
        for item in evidence
        for token in item.immutable_tokens
    }
    context_tokens = {
        token.normalized
        for prose in allowed_context_prose
        for token in extract_numeric_tokens(prose)
    }
    allowed.update(context_tokens)
    observed_count = 0
    issues: list[ValidationIssue] = []
    seen_unsupported: set[str] = set()
    for prose in candidate_prose:
        for token in extract_numeric_tokens(prose):
            observed_count += 1
            if token.normalized in allowed or token.normalized in seen_unsupported:
                continue
            seen_unsupported.add(token.normalized)
            issues.append(
                ValidationIssue(
                    gate="numeric_fidelity",
                    code="unsupported_numeric_token",
                    severity="blocking",
                    message=(
                        f"Numeric token '{token.raw}' is not present in approved evidence."
                    ),
                    observed=token.raw,
                )
            )
    return ValidationResult(
        passed=not any(issue.severity == "blocking" for issue in issues),
        issues=tuple(issues),
        metrics={
            "approved_evidence_count": len(evidence),
            "allowed_context_numeric_tokens": len(context_tokens),
            "numeric_tokens_checked": observed_count,
            "unsupported_numeric_tokens": len(issues),
            "validation_schema_version": VALIDATION_SCHEMA_VERSION,
        },
    )
