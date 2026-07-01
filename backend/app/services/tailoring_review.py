"""Build and persist transparent tailoring explanations."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tailoring_review import TailoringReview
from ..schemas.tailor import ATSScoreResult, JDAnalysisResult, SkillMatchResult, TailoredCVResult


def build_review(
    application_id: str,
    analysis: JDAnalysisResult,
    skill_match: SkillMatchResult,
    ats: ATSScoreResult,
    tailored: TailoredCVResult,
    cv_document_id: str,
    cl_document_id: str,
    template_id: str,
    variant: str,
) -> dict[str, Any]:
    covered = [item.keyword for item in ats.keyword_matches if item.found]
    missing = [item.keyword for item in ats.keyword_matches if not item.found]
    evidence = [
        {"requirement": skill, "evidence": f"Matched in master CV/profile evidence: {skill}", "confidence": "high"}
        for skill in skill_match.matched
    ]
    weak = [
        {
            "requirement": requirement,
            "reason": "Not enough grounded evidence in the profile or master CV.",
            "suggestion": "Do not claim unless you can confirm relevant experience.",
        }
        for requirement in list(dict.fromkeys(skill_match.missing + ats.unsupported_gaps))
    ]
    warnings = [
        {"severity": "medium", "message": message}
        for message in list(dict.fromkeys(
            tailored.fabrication_warnings + tailored.structural_warnings + ats.format_warnings
        ))
    ]
    return {
        "application_id": application_id,
        "match_summary": {
            "role_title": analysis.role_title,
            "overall_match": round(skill_match.match_pct),
            "summary": tailored.tailoring_notes or f"Tailored for {analysis.role_title}.",
        },
        "ats_keyword_coverage": {
            "covered": covered,
            "missing": missing,
            "coverage_pct": round(100 * len(covered) / max(1, len(covered) + len(missing))),
        },
        "evidence_used": evidence,
        "weak_or_unsupported_requirements": weak,
        "warnings": warnings,
        "documents": [
            {"id": cv_document_id, "type": "cv", "template_id": template_id},
            {"id": cl_document_id, "type": "cover_letter", "template_id": template_id},
        ],
        "template_id": template_id,
        "variant": variant,
        "created_at": datetime.utcnow().isoformat(),
    }


async def save_review(db: AsyncSession, review: dict[str, Any]) -> TailoringReview:
    row = TailoringReview(
        application_id=review["application_id"],
        cv_document_id=review["documents"][0]["id"],
        cl_document_id=review["documents"][1]["id"],
        review_json=review,
        template_id=review["template_id"],
        variant=review["variant"],
    )
    db.add(row)
    await db.flush()
    return row


async def latest_review(db: AsyncSession, application_id: str) -> dict[str, Any] | None:
    result = await db.execute(
        select(TailoringReview)
        .where(TailoringReview.application_id == application_id)
        .order_by(desc(TailoringReview.created_at))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.review_json if row else None
