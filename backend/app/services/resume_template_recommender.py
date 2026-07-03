"""Deterministic template recommendation from role and evidence signals."""
from __future__ import annotations
from typing import Any
from ..schemas.tailor import JDAnalysisResult


def recommend_templates(jd_analysis: JDAnalysisResult, profile_summary: dict[str, Any], master_cv: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([
        jd_analysis.role_title, jd_analysis.seniority_level or "",
        " ".join(jd_analysis.responsibilities),
    ]).lower()
    evidence_count = len(master_cv.get("experience", [])) + len(master_cv.get("projects", []))
    density = "high" if evidence_count >= 6 else "medium" if evidence_count >= 3 else "low"
    scored: dict[str, int] = {"ats_classic": 1}
    if any(x in text for x in ("head", "director", "senior", "leadership")):
        scored.update({"senior_leadership": 6, "executive_uk_2_page": 5})
    if any(x in text for x in ("project", "programme", "delivery", "transformation")):
        scored["project_delivery"] = scored.get("project_delivery", 0) + 5
    if any(x in text for x in ("consult", "advisory", "client")):
        scored["consulting_clean"] = scored.get("consulting_clean", 0) + 5
    if any(x in text for x in ("product", "software", "platform", " ai ", "technical")):
        scored["tech_product"] = scored.get("tech_product", 0) + 5
    if any(x in text for x in ("contract", "freelance", "day rate")):
        scored["contractor_freelance"] = scored.get("contractor_freelance", 0) + 5
    if profile_summary.get("career_switch"):
        scored["career_switcher"] = 7
    order = ["ats_classic", "modern_compact", "executive_uk_2_page", "consulting_clean", "project_delivery", "contractor_freelance", "tech_product", "career_switcher", "senior_leadership", "minimal_one_page"]
    ranked = sorted(scored, key=lambda item: (-scored[item], order.index(item)))[:2]
    return {"recommendations": [{
        "template_id": item, "confidence": "high" if scored[item] >= 6 else "medium" if scored[item] >= 3 else "low",
        "reason": {"role_seniority": jd_analysis.seniority_level, "job_type": jd_analysis.contract_details.contract_type,
                   "evidence_density": density, "ats_safety": "ATS-safe single-column layout",
                   "recommended_page_target": "two_page" if density == "high" else "auto",
                   "explanation": "Deterministic match from role type, seniority, and available evidence."},
    } for item in ranked]}
