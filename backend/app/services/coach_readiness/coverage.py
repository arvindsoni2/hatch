"""Deterministic competency and story coverage for an application.

The match key is internal. Responses always keep the first-seen original text.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application
from app.models.coach_readiness import CoachCompetencyOverride
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.story import Story
from app.repositories.story_repository import StoryRepository

from .contracts import (
    Competency,
    CompetencyCoverage,
    CoverageGap,
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
    CoverageStory,
)

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
    overrides = (
        await db.execute(
            select(CoachCompetencyOverride).where(
                CoachCompetencyOverride.application_id == application_id
            )
        )
    ).scalars().all()
    stories = await StoryRepository(db).list_all_active_orm()
    return build_coverage(
        application_id=application_id,
        competencies=await _competencies_for_application(db, application),
        stories=stories,
        overrides=_override_map(overrides),
        covered_min=(
            settings.HATCH_COACH_COVERAGE_COVERED_MIN
            if covered_min is None
            else covered_min
        ),
        thin_min=(
            settings.HATCH_COACH_COVERAGE_THIN_MIN if thin_min is None else thin_min
        ),
    )


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
            overrides={},
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
    return CoverageOverview(gaps=tuple(gaps))


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
