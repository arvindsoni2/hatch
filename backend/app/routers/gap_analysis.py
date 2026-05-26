"""JD-to-Resume gap analysis endpoint."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends
from ..database import get_db
from ..models.job import JobPosting
from ..agents.tools.profile_loader import load_profile

router = APIRouter(prefix="/api/v2/jobs", tags=["gap-analysis"])

# Minimum word length for a keyword to be considered meaningful
_MIN_KW_LEN = 3


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful lowercase word tokens from text."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", text)
    stopwords = {
        "the", "and", "for", "with", "that", "this", "you", "will", "are",
        "our", "your", "have", "has", "been", "from", "they", "their", "into",
        "about", "would", "should", "could", "must", "able", "well", "also",
        "work", "role", "team", "job", "experience", "skills", "required",
        "responsibilities", "including", "key", "strong", "excellent", "proven",
        "working", "looking", "join", "based", "across", "within",
    }
    return [w.lower() for w in words if w.lower() not in stopwords]


def _count_keyword_frequency(text: str, keywords: list[str]) -> dict[str, int]:
    """Return frequency count for each keyword in text."""
    text_lower = text.lower()
    return {kw: len(re.findall(r"\b" + re.escape(kw) + r"\b", text_lower)) for kw in keywords}


@router.get("/{job_id}/gap-analysis")
async def job_gap_analysis(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compare the job's requirements against the user's profile skills.

    Returns matched skills, missing skills, match percentage, and
    prioritised recommendations based on JD keyword frequency.
    """
    result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    jd_text = f"{job.title or ''} {job.description or ''}"
    if not jd_text.strip():
        return {
            "matched_skills": [],
            "missing_skills": [],
            "match_percentage": 0,
            "recommendations": ["No job description available for analysis."],
        }

    try:
        profile = load_profile()
    except Exception:
        raise HTTPException(status_code=500, detail="Profile not configured")

    # Collect all profile skills as a flat list
    profile_skills: list[str] = (
        list(profile.skills.primary)
        + list(profile.skills.secondary)
        + list(profile.skills.certifications)
    )

    if not profile_skills:
        return {
            "matched_skills": [],
            "missing_skills": [],
            "match_percentage": 0,
            "recommendations": ["No skills configured in your profile."],
        }

    jd_lower = jd_text.lower()
    matched: list[str] = []
    missing: list[str] = []

    for skill in profile_skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, jd_lower):
            matched.append(skill)
        else:
            missing.append(skill)

    # Also check what JD keywords are NOT in profile at all
    jd_keywords = _extract_keywords(jd_text)
    profile_kw_set = {w.lower() for s in profile_skills for w in s.split()}
    jd_only = [kw for kw in set(jd_keywords) if kw not in profile_kw_set and len(kw) > 4]
    freq = _count_keyword_frequency(jd_text, jd_only)
    top_jd_gaps = sorted(
        [(kw, count) for kw, count in freq.items() if count >= 2],
        key=lambda x: -x[1],
    )[:5]

    total = len(profile_skills)
    match_pct = round(len(matched) / total * 100) if total else 0

    recommendations: list[str] = []
    if missing:
        recommendations.append(
            f"You match {len(matched)}/{total} profile skills. "
            f"Top gaps: {', '.join(missing[:3])}"
        )
    for kw, count in top_jd_gaps:
        recommendations.append(
            f"'{kw}' appears {count}x in the JD but is not in your profile — consider adding it"
        )
    if not recommendations:
        recommendations.append("Great match! All your profile skills are present in the JD.")

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "match_percentage": match_pct,
        "jd_only_keywords": [kw for kw, _ in top_jd_gaps],
        "recommendations": recommendations,
    }
