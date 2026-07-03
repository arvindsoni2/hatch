"""Deterministic pre/post-generation CV quality gate."""
from __future__ import annotations
import re
from typing import Any
from .docx_quality_parser import parse_docx_quality


def _terms(analysis: Any) -> list[str]:
    keywords = analysis.ats_keywords
    return list(dict.fromkeys(keywords.technical + keywords.methodologies + keywords.domain + keywords.certifications))


def pre_generation_quality(analysis: Any, evidence: dict[str, Any], template_id: str) -> dict:
    source = str(evidence).lower()
    missing = [term for term in _terms(analysis) if term.lower() not in source]
    return {"status": "advisory" if missing else "good", "template_fit": "good",
            "keyword_gaps": missing, "weak_requirements": [
                {"requirement": term, "reason": "No strong evidence found in profile or master CV", "severity": "high"}
                for term in missing if term in analysis.requirements.must_have
            ], "template_notes": [f"{template_id} uses an ATS-safe single-column layout."]}


def post_generation_quality(path: str, structured: Any, analysis: Any, evidence: dict[str, Any]) -> dict:
    parsed = parse_docx_quality(path)
    text = parsed.pop("text")
    terms = _terms(analysis)
    covered = [term for term in terms if term.lower() in text.lower()]
    missing = [term for term in terms if term not in covered]
    coverage = round(100 * len(covered) / max(1, len(terms)))
    source_len = len(str(structured.model_dump() if hasattr(structured, "model_dump") else structured))
    required_missing = [key for key in ("summary", "skills", "experience") if not parsed["core_sections"][key]]
    high_risk = (
        parsed["text_extraction_chars"] < 800 or not parsed["contact_detection"]["name"]
        or not parsed["core_sections"]["experience"] or len(required_missing) >= 2 or coverage < 30
    )
    evidence_text = str(evidence).lower()
    unsupported = [
        {"claim": term, "reason": "Material JD term is not traceable to profile/master CV evidence", "severity": "high"}
        for term in covered if term.lower() not in evidence_text
    ]
    if unsupported:
        high_risk = True
    advisory = parsed["text_extraction_chars"] < source_len * .6 or coverage < 70
    return {
        **parsed, "ats_readability": "poor" if high_risk else "advisory" if advisory else "good",
        "detected_section_order": [key for key, present in parsed["core_sections"].items() if present],
        "keyword_coverage": {"covered": covered, "missing": missing, "coverage_pct": coverage},
        "unsupported_claims": unsupported,
        "export_confidence": "acknowledge_required" if high_risk else "review_recommended" if advisory else "good",
    }
