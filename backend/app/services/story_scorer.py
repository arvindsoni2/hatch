"""Computes the strength_score (1-10) for a Story based on usage and quality signals."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..models.story import Story

logger = logging.getLogger(__name__)

# Scoring formula (additive, capped at 10):
#   base_score         = 5
#   + times_used_bonus = min(3, times_used / 2)         # max +3 at 6+ uses
#   + star_quality     = avg(star_score) / 10 * 2       # max +2 (from session eval)
#   + recency_bonus    = 1 if used in last 30 days
#   + manual_rating    = (rating / 5) * 1               # max +1
#   - stale_penalty    = 1 if not used in 180 days

_RECENCY_DAYS = 30
_STALE_DAYS = 180


def compute_strength_score(
    story: Story,
    avg_star_score: float | None = None,
    last_used_at: datetime | None = None,
) -> float:
    """Compute the strength score for a story.

    Args:
        story: The Story ORM object.
        avg_star_score: Mean STAR structure score across evaluations that used this story (0-10).
        last_used_at: Most recent usage datetime (from story_usages table).

    Returns:
        Strength score clamped to [1.0, 10.0].
    """
    score = 5.0

    # Usage bonus: max +3 at 6+ uses
    score += min(3.0, story.times_used / 2.0)

    # STAR quality bonus: max +2
    if avg_star_score is not None:
        score += (avg_star_score / 10.0) * 2.0

    # Recency bonus: +1 if used in last 30 days
    if last_used_at:
        if datetime.utcnow() - last_used_at < timedelta(days=_RECENCY_DAYS):
            score += 1.0
        # Stale penalty: -1 if not used in 180 days
        elif datetime.utcnow() - last_used_at > timedelta(days=_STALE_DAYS):
            score -= 1.0

    # Manual rating bonus: max +1
    if story.manual_rating:
        score += (story.manual_rating / 5.0) * 1.0

    return round(max(1.0, min(10.0, score)), 2)
