"""Deterministic, auditable gates and scores for generated writing pairs."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from app.schemas.tailor import CoverLetterResult, TailoredCVResult

from .contracts import (
    BenchmarkCase,
    DimensionScore,
    DocumentScore,
    GateFinding,
    PairScore,
)

_NUMERIC_TOKEN_RE = re.compile(
    r"(?:[£$€¥][\d,]+(?:\.\d+)?(?:[KMBkm+]*)|"
    r"\b\d[\d,]*(?:\.\d+)?(?:[KMBkm%+]*)\b)",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]|\b(?:PLACEHOLDER|TODO|TBD)\b", re.IGNORECASE)
_LATEX_RE = re.compile(r"\\(?:textsterling|frac|begin|end)\b|\$[^$]+\$", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z0-9£$€¥%+.-]+")

_CV_WEIGHTS = {
    "grounding": 0.30,
    "jd_coverage": 0.25,
    "structure": 0.20,
    "evidence_relevance": 0.15,
    "readability": 0.10,
}
_CL_WEIGHTS = {
    "grounding": 0.35,
    "jd_coverage": 0.25,
    "structure": 0.15,
    "evidence_relevance": 0.15,
    "readability": 0.10,
}


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _achievement_text(item: Any) -> str:
    return str(item.get("text", "")) if isinstance(item, dict) else str(item)


def _source_text(case: BenchmarkCase) -> str:
    master = case.master_cv
    parts: list[str] = []
    variants = master.get("summary_variants", {})
    if isinstance(variants, dict):
        parts.extend(str(value) for value in variants.values())
    skills = master.get("skills", {})
    groups = skills.values() if isinstance(skills, dict) else skills
    for group in groups or []:
        if isinstance(group, dict):
            parts.append(str(group.get("category") or group.get("display_name") or ""))
            parts.extend(str(item) for item in group.get("items", []) if item)
    for experience in master.get("experience", []):
        if not isinstance(experience, dict):
            continue
        parts.extend(
            str(experience.get(key, "")) for key in ("role", "company", "period")
        )
        parts.extend(_achievement_text(item) for item in experience.get("achievements", []))
    for education in master.get("education", []):
        if isinstance(education, dict):
            for value in education.values():
                if isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, list):
                    parts.extend(str(item) for item in value)
        else:
            parts.append(str(education))
    parts.extend(str(item) for item in master.get("certifications", []))
    return " ".join(item for item in parts if item)


def _cv_text(cv: TailoredCVResult) -> str:
    parts = [cv.summary]
    for group in cv.skills:
        parts.append(str(group.get("category") or group.get("display_name") or ""))
        parts.extend(str(item) for item in group.get("items", []) if item)
    for experience in cv.experience:
        parts.extend([experience.role, experience.company, experience.period])
        parts.extend(experience.achievements)
    for education in cv.education:
        parts.extend(
            [
                education.qualification,
                education.institution,
                education.year,
                education.field,
                education.location,
                *education.details,
            ]
        )
    parts.extend(cv.certifications)
    return " ".join(item for item in parts if item)


def _cover_letter_text(letter: CoverLetterResult) -> str:
    return " ".join(
        [letter.subject_line, letter.greeting, *letter.body_paragraphs, letter.sign_off]
    )


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _finding(code: str, message: str, document: str) -> GateFinding:
    return GateFinding(code=code, message=message, document=document)  # type: ignore[arg-type]


def _structure_gates(case: BenchmarkCase, cv: TailoredCVResult) -> list[GateFinding]:
    findings: list[GateFinding] = []
    actual_roles = [(item.role, item.company, item.period) for item in cv.experience]
    expected_roles = [(item.role, item.company, item.period) for item in case.expected_facts.roles]
    if actual_roles != expected_roles:
        findings.append(
            _finding("role_structure_mismatch", "CV roles, companies, or periods differ from source", "cv")
        )
    for index, expected in enumerate(case.expected_facts.roles):
        actual_count = len(cv.experience[index].achievements) if index < len(cv.experience) else 0
        if actual_count != expected.achievement_count:
            findings.append(
                _finding(
                    "achievement_count_mismatch",
                    f"Role {expected.role!r} expected {expected.achievement_count} bullets, got {actual_count}",
                    "cv",
                )
            )

    if cv.certifications != case.expected_facts.certifications:
        findings.append(
            _finding("certification_mismatch", "CV certifications differ from source", "cv")
        )

    if len(cv.education) != len(case.expected_facts.education):
        findings.append(_finding("education_mismatch", "CV education count differs from source", "cv"))
    else:
        for expected, actual in zip(case.expected_facts.education, cv.education, strict=True):
            if any(_normalise(str(getattr(actual, key, ""))) != _normalise(str(value)) for key, value in expected.items()):
                findings.append(
                    _finding("education_mismatch", "CV education values differ from source", "cv")
                )
                break

    source_words = _word_count(_source_text(case))
    actual_words = _word_count(_cv_text(cv))
    if source_words:
        ratio = actual_words / source_words
        lower = 1.0 - case.cv_length_tolerance
        upper = 1.0 + case.cv_length_tolerance
        if not lower <= ratio <= upper:
            findings.append(
                _finding(
                    "cv_length_tolerance",
                    f"CV word-count ratio {ratio:.3f} is outside {lower:.3f}-{upper:.3f}",
                    "cv",
                )
            )
    return findings


def _format_and_grounding_gates(
    case: BenchmarkCase,
    cv: TailoredCVResult,
    letter: CoverLetterResult,
) -> list[GateFinding]:
    findings: list[GateFinding] = []
    texts = {"cv": _cv_text(cv), "cover_letter": _cover_letter_text(letter)}
    for document, text in texts.items():
        if not text.strip():
            findings.append(_finding("empty_document", f"{document} is empty", document))
        if _PLACEHOLDER_RE.search(text):
            findings.append(
                _finding("prohibited_placeholder", f"{document} contains placeholder text", document)
            )
        if _LATEX_RE.search(text):
            findings.append(_finding("prohibited_latex", f"{document} contains LaTeX markup", document))

    allowed_numbers = {
        _normalise(token)
        for token in [
            *_NUMERIC_TOKEN_RE.findall(_source_text(case)),
            *case.expected_facts.allowed_numeric_tokens,
        ]
    }
    for document, text in texts.items():
        for token in _NUMERIC_TOKEN_RE.findall(text):
            if _normalise(token) not in allowed_numbers:
                findings.append(
                    _finding(
                        "unsupported_numeric_token",
                        f"{document} contains unsupported numeric token {token!r}",
                        document,
                    )
                )

    actual_cl_words = _word_count(" ".join(letter.body_paragraphs))
    if not 250 <= actual_cl_words <= 350:
        findings.append(
            _finding(
                "cover_letter_word_count",
                f"Cover letter body has {actual_cl_words} words; expected 250-350",
                "cover_letter",
            )
        )
    if cv.blocking_issues:
        findings.append(
            _finding("production_grounding_failure", "; ".join(cv.blocking_issues), "cv")
        )
    if letter.grounding_issues:
        findings.append(
            _finding(
                "production_grounding_failure",
                "; ".join(letter.grounding_issues),
                "cover_letter",
            )
        )
    return findings


def _target_keywords(case: BenchmarkCase) -> list[str]:
    analysis = case.jd_analysis
    candidates = [
        *analysis.requirements.must_have,
        *analysis.ats_keywords.technical,
        *analysis.ats_keywords.methodologies,
        *analysis.ats_keywords.soft_skills,
        *analysis.ats_keywords.domain,
        *analysis.ats_keywords.certifications,
    ]
    source = _normalise(_source_text(case))
    approved = {_normalise(item) for item in case.expected_facts.approved_vocabulary}
    result: list[str] = []
    for item in candidates:
        normalised = _normalise(item)
        if normalised and (normalised in source or normalised in approved) and normalised not in result:
            result.append(normalised)
    return result


def _coverage_score(targets: Iterable[str], text: str) -> tuple[float, list[str]]:
    target_list = list(targets)
    if not target_list:
        return 100.0, ["No supported target keywords were defined."]
    normalised = _normalise(text)
    found = [item for item in target_list if item in normalised]
    missing = [item for item in target_list if item not in normalised]
    score = 100.0 * len(found) / len(target_list)
    observations = [f"Covered {len(found)} of {len(target_list)} supported targets."]
    if missing:
        observations.append("Missing: " + ", ".join(missing))
    return score, observations


def _readability_score(text: str) -> tuple[float, list[str]]:
    words = [_normalise(item) for item in _WORD_RE.findall(text)]
    if not words:
        return 0.0, ["Document has no words."]
    trigrams = list(zip(words, words[1:], words[2:]))
    duplicates = sum(count - 1 for count in Counter(trigrams).values() if count > 1)
    duplicate_ratio = duplicates / max(1, len(trigrams))
    score = max(0.0, 100.0 - duplicate_ratio * 200.0)
    return round(score, 2), [f"Repeated trigram ratio: {duplicate_ratio:.3f}."]


def _document_score(
    text: str,
    targets: list[str],
    weights: dict[str, float],
) -> DocumentScore:
    coverage, coverage_notes = _coverage_score(targets, text)
    readability, readability_notes = _readability_score(text)
    raw = {
        "grounding": (100.0, ["All blocking grounding gates passed."]),
        "jd_coverage": (coverage, coverage_notes),
        "structure": (100.0, ["All blocking structure gates passed."]),
        "evidence_relevance": (coverage, coverage_notes),
        "readability": (readability, readability_notes),
    }
    dimensions = {
        name: DimensionScore(score=score, weight=weights[name], observations=notes)
        for name, (score, notes) in raw.items()
    }
    total = round(sum(item.score * item.weight for item in dimensions.values()), 2)
    return DocumentScore(total=total, dimensions=dimensions)


def score_pair(
    case: BenchmarkCase,
    cv: TailoredCVResult,
    cover_letter: CoverLetterResult,
) -> PairScore:
    gates = [
        *_structure_gates(case, cv),
        *_format_and_grounding_gates(case, cv, cover_letter),
    ]
    if any(item.blocking for item in gates):
        return PairScore(eligible=False, gates=gates)

    targets = _target_keywords(case)
    cv_score = _document_score(_cv_text(cv), targets, _CV_WEIGHTS)
    cl_score = _document_score(_cover_letter_text(cover_letter), targets, _CL_WEIGHTS)
    return PairScore(
        eligible=True,
        gates=gates,
        cv=cv_score,
        cover_letter=cl_score,
        combined=round(cv_score.total * 0.6 + cl_score.total * 0.4, 2),
    )
