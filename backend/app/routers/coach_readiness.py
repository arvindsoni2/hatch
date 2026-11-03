"""Coach readiness coverage routes (P1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..schemas.coach_readiness import (
    CompetencyCoverageRead,
    CoverageGapRead,
    CoverageMapRead,
    CoverageOverviewRead,
    CoverageOverridesWrite,
    CoverageStoryRead,
)
from ..services.coach_readiness import coverage
from ..services.coach_readiness.contracts import (
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
)

router = APIRouter(prefix="/api/coach/readiness", tags=["coach-readiness"])


def _map_read(result: CoverageMap) -> CoverageMapRead:
    return CoverageMapRead(
        application_id=result.application_id,
        covered_count=result.covered_count,
        thin_count=result.thin_count,
        gap_count=result.gap_count,
        competencies=[
            CompetencyCoverageRead(
                competency=item.competency,
                status=item.status,
                action=item.action,
                stories=[
                    CoverageStoryRead(
                        story_id=story.story_id,
                        title=story.title,
                        score=story.score,
                        has_metric=story.has_metric,
                    )
                    for story in item.stories
                ],
            )
            for item in result.competencies
        ],
    )


def _overview_read(result: CoverageOverview) -> CoverageOverviewRead:
    return CoverageOverviewRead(
        gaps=[
            CoverageGapRead(
                competency=item.competency,
                application_count=item.application_count,
            )
            for item in result.gaps
        ]
    )


@router.get("/coverage/overview", response_model=CoverageOverviewRead)
async def get_coverage_overview(
    db: AsyncSession = Depends(get_db),
) -> CoverageOverviewRead:
    return _overview_read(await coverage.coverage_overview(db))


@router.get("/coverage", response_model=CoverageMapRead)
async def get_coverage(
    application_id: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> CoverageMapRead:
    result = await coverage.coverage_for_application(db, application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _map_read(result)


@router.put(
    "/coverage/{application_id}/overrides",
    response_model=CoverageMapRead,
)
async def put_coverage_overrides(
    application_id: str,
    payload: CoverageOverridesWrite,
    db: AsyncSession = Depends(get_db),
) -> CoverageMapRead:
    if not settings.HATCH_COACH_STORY_COVERAGE_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    result = await coverage.replace_overrides(
        db,
        application_id,
        [
            CoverageOverride(
                original=item.original,
                replacement=item.replacement,
                hidden=item.hidden,
            )
            for item in payload.overrides
        ],
    )
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _map_read(result)
