"""Scoring insights endpoint — threshold feedback and score distribution."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.job_score import JobScore
from ..agents.tools.profile_loader import load_profile

router = APIRouter(prefix="/api/v2/scoring", tags=["scoring"])


class ScoreBucket(BaseModel):
    bucket: str
    count: int


class ScoringInsights(BaseModel):
    threshold: float
    scored_last_7d: int
    above_threshold: int
    in_band_below: int          # jobs just below threshold (threshold-0.15 to threshold)
    avg_score: float | None
    distribution: list[ScoreBucket]
    recommendation: str | None


@router.get("/insights", response_model=ScoringInsights)
async def get_scoring_insights(db: AsyncSession = Depends(get_db)) -> ScoringInsights:
    """Return threshold context + score distribution for the last 7 days.

    Helps users understand why their approval queue may be empty and
    surfaces actionable recommendations.
    """
    try:
        profile = load_profile()
        threshold = getattr(profile.scoring, "shortlist_threshold", 0.75)
    except Exception:
        threshold = 0.75

    since = datetime.utcnow() - timedelta(days=7)

    # All scores in the last 7 days
    result = await db.execute(
        select(JobScore.overall_score).where(JobScore.scored_at >= since)
    )
    scores: list[float] = [row[0] for row in result.all() if row[0] is not None]

    if not scores:
        return ScoringInsights(
            threshold=threshold,
            scored_last_7d=0,
            above_threshold=0,
            in_band_below=0,
            avg_score=None,
            distribution=[],
            recommendation="No jobs have been scored in the last 7 days. Trigger a scrape to get started.",
        )

    band_low = threshold - 0.15
    above = sum(1 for s in scores if s >= threshold)
    in_band = sum(1 for s in scores if band_low <= s < threshold)
    avg = round(sum(scores) / len(scores), 3)

    # Build 10-bucket distribution (0-10%, 10-20%, ..., 90-100%)
    buckets: dict[str, int] = {f"{i*10}-{(i+1)*10}%": 0 for i in range(10)}
    for s in scores:
        idx = min(9, int(s * 10))
        key = f"{idx*10}-{(idx+1)*10}%"
        buckets[key] = buckets.get(key, 0) + 1
    distribution = [ScoreBucket(bucket=k, count=v) for k, v in buckets.items()]

    # Build recommendation
    recommendation: str | None = None
    pct = int(threshold * 100)
    avg_pct = int(avg * 100)
    in_band_pct = int(band_low * 100)
    if above == 0 and in_band > 0:
        recommendation = (
            f"No jobs above your {pct}% threshold this week, but {in_band} scored "
            f"{in_band_pct}–{pct}%. Lowering your threshold to {in_band_pct}% would surface them."
        )
    elif above < 3 and in_band > 0:
        recommendation = (
            f"Only {above} job{'s' if above != 1 else ''} above your {pct}% threshold this week. "
            f"{in_band} more scored {in_band_pct}–{pct}%. Consider lowering to {in_band_pct}%."
        )
    elif avg_pct < pct - 10:
        recommendation = (
            f"Your threshold is {pct}% but the average score this week was {avg_pct}%. "
            f"Lowering to {avg_pct + 5}% would surface more roles."
        )

    return ScoringInsights(
        threshold=threshold,
        scored_last_7d=len(scores),
        above_threshold=above,
        in_band_below=in_band,
        avg_score=avg,
        distribution=distribution,
        recommendation=recommendation,
    )
