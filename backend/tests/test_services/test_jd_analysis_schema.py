"""Guard: jd_analysis.j2 prompt keys must match the Pydantic schema.

Each test passes a raw blob that mirrors the prompt's documented JSON structure
and asserts the parsed result carries the expected values. If prompt and schema
diverge, _parse_jd_analysis silently drops unknown keys and the assertions fail.
"""
from __future__ import annotations

from app.services.jd_analyser import _parse_jd_analysis

MACE_BLOB = {
    "role_title": "Enterprise Architect (Business Systems)",
    "seniority_level": "lead",
    "contract_details": {
        "contract_type": "permanent",
        "ir35_status": "unknown",
        "rate_range": "£120,000–£140,000",
        "location": "London / Hybrid",
    },
    "company_context": {
        "company_name": "Mace",
        "sector": "construction",
        "size": "enterprise",
        "culture_indicators": ["collaborative", "delivery-focused", "structured"],
    },
    "requirements": {
        "must_have": ["TOGAF", "Stakeholder management", "Business Architecture"],
        "nice_to_have": ["BIM", "Archimate"],
        "years_experience": 10,
    },
    "responsibilities": [
        "Define and govern enterprise architecture across Mace programmes",
        "Align IT strategy with business transformation goals",
    ],
    "ats_keywords": {
        "technical": ["TOGAF", "Archimate", "ERP", "API"],
        "methodologies": ["PRINCE2", "Agile", "TOGAF ADM"],
        "soft_skills": ["stakeholder management", "communication"],
        "domain": ["construction", "infrastructure", "business systems"],
        "certifications": ["TOGAF 9", "PRINCE2"],
    },
    "tone_analysis": {
        "formality": "formal",
        "emphasis": "leadership",
        "red_flags": [],
    },
}


def test_company_name_populates():
    """company_context.company_name in the prompt blob must reach the parsed result."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert result.company_context.company_name == "Mace"


def test_rate_range_populates():
    """contract_details.rate_range in the prompt blob must reach the parsed result."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert result.contract_details.rate_range == "£120,000–£140,000"


def test_sector_populates():
    """company_context.sector must always pass through (baseline sanity check)."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert result.company_context.sector == "construction"


def test_contract_type_populates():
    """contract_details.contract_type must be preserved — drives contractor vs permanent framing."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert result.contract_details.contract_type == "permanent"


def test_culture_indicators_populate():
    """company_context.culture_indicators must map correctly (prompt previously used culture_signals)."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert "collaborative" in result.company_context.culture_indicators


def test_size_populates():
    """company_context.size must map correctly (prompt previously used size_signals)."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert result.company_context.size == "enterprise"


def test_education_absent_from_requirements():
    """education must NOT appear in Requirements — it was dropped from the prompt."""
    result = _parse_jd_analysis(MACE_BLOB, 1000)
    assert not hasattr(result.requirements, "education")


def test_null_company_name_stays_none():
    """If company name is genuinely absent, company_name must be None — not a placeholder."""
    blob = {**MACE_BLOB, "company_context": {**MACE_BLOB["company_context"], "company_name": None}}
    result = _parse_jd_analysis(blob, 500)
    assert result.company_context.company_name is None
