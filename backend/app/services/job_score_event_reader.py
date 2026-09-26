"""Resolve score content for product reads without copying it into event storage."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_score import JobScore


async def read_job_score_event_payloads(
    raw_payloads: Iterable[object], db: AsyncSession
) -> list[dict[str, Any]]:
    """Batch-resolve canonical score IDs, scoped to each event's job identity.

    Legacy inline payloads remain readable. Reference-bearing events only gain
    content in fresh response dictionaries; no ORM event is mutated or flushed.
    Missing, malformed or cross-job references never resolve another job's text.
    """
    payloads = []
    references = []
    for raw in raw_payloads:
        try:
            decoded = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            decoded = None
        payload = dict(decoded) if isinstance(decoded, dict) else {}
        score_id = None
        if "score_ref" in payload:
            for field in (
                "reasoning",
                "fit_reasoning",
                "strengths",
                "score_gaps",
                "keyword_matches",
                "keyword_misses",
            ):
                payload.pop(field, None)
            reference = payload["score_ref"]
            if isinstance(reference, str) and reference.startswith("job-score:"):
                candidate = reference.removeprefix("job-score:")
                if len(candidate) == 36:
                    try:
                        score_id = str(UUID(candidate))
                    except ValueError:
                        pass
        payloads.append(payload)
        references.append(score_id)
    ids = {reference for reference in references if reference is not None}
    scores = (
        {
            row.id: row
            for row in await db.scalars(select(JobScore).where(JobScore.id.in_(ids)))
        }
        if ids
        else {}
    )
    for payload, score_id in zip(payloads, references):
        score = scores.get(score_id)
        if score is not None and payload.get("job_id") == score.job_id:
            payload.update(
                reasoning=score.reasoning,
                fit_reasoning=score.fit_reasoning,
                strengths=score.strengths or [],
                score_gaps=score.score_gaps or [],
                keyword_matches=score.keyword_matches or [],
                keyword_misses=score.keyword_misses or [],
            )
    return payloads
