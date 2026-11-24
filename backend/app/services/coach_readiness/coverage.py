"""Deterministic competency and story coverage for an application.

The match key is internal. Responses always keep the first-seen original text.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.config import settings
from app.models.application import Application
from app.models.coach_readiness import CoachCompetencyOverride, CoachDerivedText
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.story import Story
from app.repositories.story_repository import StoryRepository
from app.services.ai_setup import load_runtime

from .contracts import (
    Competency,
    CompetencyCoverage,
    CoverageGap,
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
    CoverageStory,
    GenerationRequest,
    SourceRef,
    ValidatedOutput,
    finalise_generation,
    input_fingerprint,
)
from .grounding import grounding_violations
from .tiers import load_tier_map

_STOPWORDS_PATH = Path(__file__).with_name("stopwords_en.txt")
_STOPWORDS = frozenset(
    _STOPWORDS_PATH.read_text(encoding="utf-8").split()
)
_COMPETENCY_CAP = 12
_MAX_STORIES = 2


def match_key(text: str) -> str:
    """Lowercase, trim, collapse whitespace and remove stop words."""
    words = str(text).casefold().split()
    return " ".join(word for word in words if word not in _STOPWORDS)


def competency_list(
    *,
    keyword_misses: Sequence[object] | None,
    keyword_matches: Sequence[object] | None,
    skills: Sequence[object] | None,
) -> tuple[Competency, ...]:
    """Build the ordered, de-duplicated competency list for a job."""
    seen: dict[str, Competency] = {}
    for group in (keyword_misses, keyword_matches, skills):
        for value in group or ():
            if not isinstance(value, str):
                continue
            original = value.strip()
            key = match_key(original)
            if not key or key in seen:
                continue
            seen[key] = Competency(text=original, match_key=key)
            if len(seen) == _COMPETENCY_CAP:
                return tuple(seen.values())
    return tuple(seen.values())


def story_word_set(story: Story) -> frozenset[str]:
    """Match-key words of a story's tags, skills and title."""
    words: set[str] = set()
    for value in [*(story.tags or []), *(story.skills or []), story.title or ""]:
        words.update(match_key(str(value)).split())
    return frozenset(words)


def build_coverage(
    *,
    application_id: str,
    competencies: Sequence[Competency],
    stories: Sequence[Story],
    overrides: Mapping[str, CoverageOverride],
    covered_min: float,
    thin_min: float,
) -> CoverageMap:
    """Apply overrides and score every competency against the active stories."""
    active = [story for story in stories if story.is_active]
    story_words = {story.id: story_word_set(story) for story in active}

    items: list[CompetencyCoverage] = []
    for competency in competencies:
        override = overrides.get(competency.match_key)
        if override is not None and override.hidden:
            continue
        display = (
            override.replacement
            if override is not None and override.replacement
            else competency.text
        )
        words = set(competency.match_key.split())
        scored: list[tuple[float, Story]] = []
        if words:
            for story in active:
                overlap = len(words & story_words[story.id])
                if overlap:
                    scored.append((overlap / len(words), story))
        scored.sort(
            key=lambda item: (
                -item[0],
                -float(item[1].strength_score or 0.0),
                item[1].id,
            )
        )
        best = scored[: _MAX_STORIES]
        best_score = best[0][0] if best else 0.0
        if best_score >= covered_min and best[0][1].result:
            status, action = "covered", "use"
        elif best_score >= thin_min:
            status, action = "thin", "strengthen"
        else:
            status, action = "gap", "draft"
        items.append(
            CompetencyCoverage(
                competency=display,
                status=status,
                action=action,
                label=competency.label,
                stories=tuple(
                    CoverageStory(
                        story_id=story.id,
                        title=story.title,
                        score=round(score, 4),
                        has_metric=bool(story.metrics),
                    )
                    for score, story in best
                ),
            )
        )
    return CoverageMap(application_id=application_id, competencies=tuple(items))


def _override_map(rows: Sequence[CoachCompetencyOverride]) -> dict[str, CoverageOverride]:
    return {
        match_key(row.original): CoverageOverride(
            original=row.original,
            replacement=row.replacement,
            hidden=bool(row.hidden),
        )
        for row in rows
    }


async def _overrides_for_application(
    db: AsyncSession, application_id: str
) -> dict[str, CoverageOverride]:
    rows = (
        await db.execute(
            select(CoachCompetencyOverride).where(
                CoachCompetencyOverride.application_id == application_id
            )
        )
    ).scalars().all()
    return _override_map(rows)


async def _competencies_for_application(
    db: AsyncSession, application: Application
) -> tuple[Competency, ...]:
    if application.job_id is None:
        return ()
    score = (
        await db.execute(select(JobScore).where(JobScore.job_id == application.job_id))
    ).scalar_one_or_none()
    job = (
        await db.execute(select(JobPosting).where(JobPosting.id == application.job_id))
    ).scalar_one_or_none()
    return competency_list(
        keyword_misses=score.keyword_misses if score else (),
        keyword_matches=score.keyword_matches if score else (),
        skills=job.skills if job else (),
    )


async def coverage_for_application(
    db: AsyncSession,
    application_id: str,
    *,
    covered_min: float | None = None,
    thin_min: float | None = None,
) -> CoverageMap | None:
    application = (
        await db.execute(
            select(Application).where(
                Application.id == application_id,
                Application.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if application is None:
        return None
    stories = await StoryRepository(db).list_all_active_orm()
    competencies = await _competencies_for_application(db, application)
    if len(competencies) < 5:
        competencies = (*competencies, *await _extracted_competencies(db, application))
    return build_coverage(
        application_id=application_id,
        competencies=competencies,
        stories=stories,
        overrides=await _overrides_for_application(db, application_id),
        covered_min=(
            settings.HATCH_COACH_COVERAGE_COVERED_MIN
            if covered_min is None
            else covered_min
        ),
        thin_min=(
            settings.HATCH_COACH_COVERAGE_THIN_MIN if thin_min is None else thin_min
        ),
    )


_COMPETENCY_TASK = "coach.readiness.competency_extract"
_COMPETENCY_PROMPT = "competency-extract-v1"
_EXTRACTED_LABEL = "from the job description"
_MAX_EXTRACTED = 4
_MAX_INPUT_CHARS = 4_500  # ≤ 1,200 tokens at 4 characters per token (AC34).
# A failed extraction is not retried on every read (P8 repair cycle 1).
_EXTRACT_FAILURE_TTL_SECONDS = 600
_EXTRACT_INFLIGHT: set[str] = set()
_EXTRACT_TASKS: set[asyncio.Task] = set()
_EXTRACT_FAILED: dict[str, float] = {}
_SKILL_WORDS = (
    "experience", "proficiency", "knowledge", "familiarity", "expertise",
    "skilled", "responsible for", "must have", "required", "ownership of",
)
_BULLET_PREFIXES = ("-", "•", "*", "–")


def requirement_lines(description: str) -> str:
    """Requirement-like lines only: bullets and lines naming skills (§10)."""
    lines: list[str] = []
    for raw in str(description or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line[0] in _BULLET_PREFIXES or any(word in line.casefold() for word in _SKILL_WORDS):
            lines.append(line)
    return "\n".join(lines)[:_MAX_INPUT_CHARS]


def _competencies_from(output: Mapping) -> tuple[Competency, ...]:
    items: list[Competency] = []
    seen: set[str] = set()
    for value in output.get("competencies", ()):
        if not isinstance(value, str) or not value.strip():
            continue
        key = match_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(
            Competency(text=value.strip(), match_key=key, label=_EXTRACTED_LABEL)
        )
        if len(items) == _MAX_EXTRACTED:
            break
    return tuple(items)


async def _competency_call(text: str) -> dict:
    from .explain import _route_base_url

    tier = load_tier_map()["T"]
    payload = {
        "model": tier.model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with a competencies array of at most four "
                    "short skill names found in the job requirements."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": tier.max_output_tokens,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(tier.deadline_s)) as client:
        response = await client.post(
            f"{_route_base_url(tier.route)}/chat/completions", json=payload
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("competency extraction is not JSON")
    return json.loads(content[start : end + 1])


def _extract_key(job_id: str, cache_key: str) -> str:
    return f"{job_id}:{cache_key}"


async def _extracted_competencies(
    db: AsyncSession, application: Application
) -> tuple[Competency, ...]:
    """Cached Tier T extraction only; reads never call the model (spec §7.4).

    A cache miss starts one background generation per job and description
    hash, deduped in process; a failure marks the key so it is not retried
    on every read.
    """
    if not settings.HATCH_COACH_STORY_COVERAGE_ENABLED:
        return ()
    if load_runtime().get("ai_mode") not in {"local", "custom"}:
        return ()
    if application.job_id is None:
        return ()
    job = await db.get(JobPosting, application.job_id)
    if job is None:
        return ()
    text = requirement_lines(job.description or "")
    if not text:
        return ()

    cache_key = (
        f"competency:{job.id}:"
        f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
    )
    cached = (
        await db.execute(
            select(CoachDerivedText).where(CoachDerivedText.cache_key == cache_key)
        )
    ).scalar_one_or_none()
    if cached is not None and isinstance(cached.text_json, Mapping):
        return _competencies_from(cached.text_json)

    key = _extract_key(job.id, cache_key)
    if key in _EXTRACT_INFLIGHT:
        return ()
    if _EXTRACT_FAILED.get(key, 0.0) > time.monotonic():
        return ()
    _EXTRACT_INFLIGHT.add(key)
    sources = (
        SourceRef("job", job.id, job.updated_at.isoformat() if job.updated_at else ""),
    )
    task = asyncio.create_task(
        _extract_and_cache(job.id, sources, cache_key, text, key)
    )
    _EXTRACT_TASKS.add(task)
    task.add_done_callback(_EXTRACT_TASKS.discard)
    return ()


async def _extract_and_cache(
    job_id: str, sources: tuple[SourceRef, ...], cache_key: str, text: str, key: str
) -> None:
    try:
        output = await _competency_call(text)
        case = {"job_id": job_id, "job_description": text}
        if grounding_violations("competency_extract", output, case):
            _EXTRACT_FAILED[key] = time.monotonic() + _EXTRACT_FAILURE_TTL_SECONDS
            return
        request = GenerationRequest(
            task_id=_COMPETENCY_TASK,
            kind="competency",
            cache_key=cache_key,
            input_fingerprint=input_fingerprint(
                _COMPETENCY_TASK, sources, {"job": job_id}
            ),
            sources=sources,
            params={"job": job_id},
        )
        async with database.AsyncSessionLocal() as db:
            outcome = await finalise_generation(
                db,
                request,
                ValidatedOutput(
                    text_json=output,
                    model_identity=load_tier_map()["T"].model_id or "",
                    prompt_version=_COMPETENCY_PROMPT,
                ),
                datetime.now(UTC),
            )
            if outcome.status == "succeeded":
                # The background session owns this transaction: without the
                # commit, the flushed cache row is rolled back on close.
                await db.commit()
        if outcome.status == "fenced":
            _EXTRACT_FAILED[key] = time.monotonic() + _EXTRACT_FAILURE_TTL_SECONDS
    except Exception:
        _EXTRACT_FAILED[key] = time.monotonic() + _EXTRACT_FAILURE_TTL_SECONDS
    finally:
        _EXTRACT_INFLIGHT.discard(key)


async def coverage_overview(
    db: AsyncSession,
    *,
    covered_min: float | None = None,
    thin_min: float | None = None,
) -> CoverageOverview:
    applications = (
        await db.execute(
            select(Application).where(
                Application.status == "interview",
                Application.is_active.is_(True),
            )
        )
    ).scalars().all()
    stories = await StoryRepository(db).list_all_active_orm()
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for application in applications:
        result = build_coverage(
            application_id=application.id,
            competencies=await _competencies_for_application(db, application),
            stories=stories,
            overrides=await _overrides_for_application(db, application.id),
            covered_min=(
                settings.HATCH_COACH_COVERAGE_COVERED_MIN
                if covered_min is None
                else covered_min
            ),
            thin_min=(
                settings.HATCH_COACH_COVERAGE_THIN_MIN
                if thin_min is None
                else thin_min
            ),
        )
        for item in result.competencies:
            if item.status != "gap":
                continue
            key = match_key(item.competency)
            counts[key] = counts.get(key, 0) + 1
            display.setdefault(key, item.competency)
    gaps = [
        CoverageGap(competency=display[key], application_count=count)
        for key, count in counts.items()
        if count >= 2
    ]
    gaps.sort(key=lambda item: (-item.application_count, item.competency.casefold()))
    from .signals import load_signals  # local import: signals reads coverage keys

    return CoverageOverview(gaps=tuple(gaps), signals=await load_signals(db))


async def replace_overrides(
    db: AsyncSession,
    application_id: str,
    overrides: Sequence[CoverageOverride],
) -> CoverageMap | None:
    exists = (
        await db.execute(
            select(Application.id).where(
                Application.id == application_id,
                Application.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        return None
    await db.execute(
        delete(CoachCompetencyOverride).where(
            CoachCompetencyOverride.application_id == application_id
        )
    )
    for override in overrides:
        original = override.original.strip()
        if not original:
            continue
        db.add(
            CoachCompetencyOverride(
                application_id=application_id,
                original=original,
                replacement=(
                    override.replacement.strip() if override.replacement else None
                ),
                hidden=override.hidden,
            )
        )
    await db.flush()
    return await coverage_for_application(db, application_id)
