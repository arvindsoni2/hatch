"""Coach readiness coverage routes (P1)."""
from __future__ import annotations

from datetime import UTC, datetime

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
    DebriefQuestionRead,
    DebriefReadResponse,
    ReadinessNextActionRead,
    SaveDebriefRequest,
    SkipDebriefRequest,
)
from ..services.coach_readiness import coverage
from ..services.coach_readiness.contracts import (
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
    DebriefQuestion,
    DebriefRead,
    ReadinessError,
    SaveDebriefCommand,
)
from ..services.coach_readiness.debrief import DebriefService
from ..services.coach_readiness.next_actions import debrief_next_actions

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


def _utc_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _debrief_read(result: DebriefRead) -> DebriefReadResponse:
    return DebriefReadResponse(
        round_id=result.round_id,
        application_id=result.application_id,
        round_status=result.round_status,
        scheduled_at=_utc_z(result.scheduled_at),
        duration_minutes=result.duration_minutes,
        status=result.status,
        version=result.version,
        overall=result.overall,
        expectation=result.expectation,
        questions=[
            DebriefQuestionRead(
                id=item.id,
                text=item.text,
                source_ref=item.source_ref,
                asked=item.asked,
                rating=item.rating,
                story_id=item.story_id,
                note=item.note,
            )
            for item in result.questions
        ],
        went_well=result.went_well,
        do_differently=result.do_differently,
        notes_text=result.notes_text,
        questions_added=result.questions_added,
    )


def _readiness_error(exc: ReadinessError) -> HTTPException:
    status = {
        "invalid_state": 409,
        "version_conflict": 409,
        "not_found": 404,
        "invalid_input": 422,
        "disabled": 403,
    }.get(exc.code, 409)
    return HTTPException(status_code=status, detail=exc.code)


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


@router.get(
    "/rounds/{round_id}/debrief",
    response_model=DebriefReadResponse,
)
async def get_debrief(
    round_id: str,
    db: AsyncSession = Depends(get_db),
) -> DebriefReadResponse:
    result = await DebriefService(db).get_or_due(round_id, datetime.now(UTC))
    if result is None or (
        not settings.HATCH_COACH_DEBRIEF_ENABLED and result.status == "due"
    ):
        raise HTTPException(status_code=404, detail="not_found")
    return _debrief_read(result)


@router.put(
    "/rounds/{round_id}/debrief",
    response_model=DebriefReadResponse,
)
async def put_debrief(
    round_id: str,
    payload: SaveDebriefRequest,
    db: AsyncSession = Depends(get_db),
) -> DebriefReadResponse:
    if not settings.HATCH_COACH_DEBRIEF_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    command = SaveDebriefCommand(
        expected_version=payload.expected_version,
        overall=payload.overall,
        expectation=payload.expectation,
        questions=[
            DebriefQuestion(
                id=item.id,
                text=item.text,
                source_ref=(
                    item.source_ref.model_dump() if item.source_ref else None
                ),
                asked=item.asked,
                rating=item.rating,
                story_id=item.story_id,
                note=item.note,
            )
            for item in payload.questions
        ],
        went_well=payload.went_well,
        do_differently=payload.do_differently,
        notes_text=payload.notes_text,
    )
    try:
        result = await DebriefService(db).save(
            round_id, command, datetime.now(UTC)
        )
    except ReadinessError as exc:
        raise _readiness_error(exc) from exc
    return _debrief_read(result)


@router.post(
    "/rounds/{round_id}/debrief/skip",
    response_model=DebriefReadResponse,
)
async def skip_debrief(
    round_id: str,
    payload: SkipDebriefRequest,
    db: AsyncSession = Depends(get_db),
) -> DebriefReadResponse:
    if not settings.HATCH_COACH_DEBRIEF_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    try:
        result = await DebriefService(db).skip(
            round_id, payload.expected_version, datetime.now(UTC)
        )
    except ReadinessError as exc:
        raise _readiness_error(exc) from exc
    return _debrief_read(result)


@router.get(
    "/next-actions",
    response_model=list[ReadinessNextActionRead],
)
async def get_readiness_next_actions(
    db: AsyncSession = Depends(get_db),
) -> list[ReadinessNextActionRead]:
    if not settings.HATCH_COACH_DEBRIEF_ENABLED:
        return []
    return [
        ReadinessNextActionRead(**item)
        for item in await debrief_next_actions(db, datetime.now(UTC))
    ]


@router.get("/display-timezone")
async def get_display_timezone() -> dict[str, str | None]:
    return {"display_timezone": settings.HATCH_DISPLAY_TIMEZONE}
