"""Coach readiness coverage routes (P1)."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.coach_readiness import CoachPatternDismissal
from ..repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from ..schemas.coach_readiness import (
    CompetencyCoverageRead,
    PatternGroupRead,
    PatternGroupSectionRead,
    PatternListRead,
    PatternRead,
    PatternSupportRead,
    PatternWhyExcerptRead,
    PatternWhyRead,
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
from ..services.ai_setup import load_catalog, load_intent, load_probe_snapshot
from ..services.coach_readiness import coverage
from ..services.coach_readiness import patterns as pattern_rules
from ..services.coach_readiness.contracts import (
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
    DebriefQuestion,
    DebriefRead,
    PatternPolicy,
    ReadinessError,
    SaveDebriefCommand,
)
from ..services.coach_readiness.debrief import DebriefService
from ..services.coach_readiness.next_actions import debrief_next_actions
from ..services.coach_readiness.tiers import (
    MIN_TIER_L_RAM_GB,
    load_tier_map,
    tier_l_available,
)

router = APIRouter(prefix="/api/coach/readiness", tags=["coach-readiness"])
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


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


@router.get("/model-tiers")
async def get_model_tiers() -> dict[str, Any]:
    mapping = load_tier_map()
    catalogue = {model["id"]: model for model in load_catalog()}
    snapshot = load_probe_snapshot() or {}
    total_ram_gb = float((snapshot.get("memory") or {}).get("total_gb") or 0)
    available = tier_l_available(total_ram_gb)
    intent = load_intent()
    return {
        "tiers": [
            {
                "tier": config.tier,
                "route": config.route,
                "model_id": config.model_id,
                "display_name": catalogue.get(config.model_id or "", {}).get(
                    "display_name", config.model_id or ""
                ),
                "status": catalogue.get(config.model_id or "", {}).get(
                    "status", "promoted"
                ),
                "thinking": config.thinking,
                "max_output_tokens": config.max_output_tokens,
                "deadline_s": config.deadline_s,
            }
            for config in mapping.values()
        ],
        "tier_l": {
            "available": available,
            # A stored opt-in never takes effect on a machine below the RAM gate.
            "enabled": bool(intent.get("tier_l_enabled", False)) and available,
            "min_ram_gb": MIN_TIER_L_RAM_GB,
        },
    }


def _pattern_read(pattern) -> PatternRead:
    return PatternRead(
        fingerprint=pattern.fingerprint,
        group=PatternGroupRead(
            role_family=pattern.group.role_family,
            interview_type=pattern.group.interview_type,
            contract_version=pattern.group.contract_version,
        ),
        dimension=pattern.dimension,
        kind=pattern.kind,
        trend=pattern.trend,
        trend_label=pattern.trend_label,
        supporting=[
            PatternSupportRead(
                session_id=item.session_id,
                completed_at=_utc_z(item.completed_at) or "",
                level=item.level,
                difficulty=item.difficulty,
                role_level=item.role_level,
            )
            for item in pattern.supporting
        ],
        stale=pattern.stale,
        dismissed=pattern.dismissed,
        seen_again=pattern.seen_again,
    )


async def _pattern_sources(db: AsyncSession):
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    rows = (await db.execute(select(CoachPatternDismissal.fingerprint))).scalars()
    derived = pattern_rules.derive_patterns(
        snapshots,
        frozenset(rows),
        PatternPolicy(window_days=settings.HATCH_COACH_PATTERN_WINDOW_DAYS),
        datetime.now(UTC),
    )
    return snapshots, derived


@router.get("/patterns", response_model=PatternListRead)
async def get_readiness_patterns(
    group: str | None = Query(default=None),
    include_stale: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> PatternListRead:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        return PatternListRead(groups=[], include_stale=include_stale)
    snapshots, derived = await _pattern_sources(db)
    sections: dict[tuple[str, str, str], dict[str, Any]] = {}
    for snapshot in snapshots:
        key = (
            snapshot.role_family or "unspecified",
            snapshot.interview_type or "unspecified",
            snapshot.evaluation_contract_version,
        )
        section = sections.setdefault(
            key, {"ids": set(), "latest": snapshot.completed_at, "patterns": []}
        )
        section["ids"].add(snapshot.session_id)
        if snapshot.completed_at > section["latest"]:
            section["latest"] = snapshot.completed_at
    for pattern in derived:
        if pattern.stale and not include_stale:
            continue
        key = (
            pattern.group.role_family,
            pattern.group.interview_type,
            pattern.group.contract_version,
        )
        sections.setdefault(
            key, {"ids": set(), "latest": datetime.min, "patterns": []}
        )["patterns"].append(_pattern_read(pattern))
    if group:
        role_family, _, interview_type = group.partition("|")
        sections = {
            key: value
            for key, value in sections.items()
            if key[0] == role_family and (not interview_type or key[1] == interview_type)
        }
    ordered = sorted(
        sections.items(),
        key=lambda item: (item[1]["latest"], item[0]),
        reverse=True,
    )
    return PatternListRead(
        groups=[
            PatternGroupSectionRead(
                role_family=key[0],
                interview_type=key[1],
                contract_version=key[2],
                session_count=len(value["ids"]),
                patterns=value["patterns"],
            )
            for key, value in ordered
        ],
        include_stale=include_stale,
    )


@router.get("/patterns/{fingerprint}/why", response_model=PatternWhyRead)
async def get_readiness_pattern_why(
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
) -> PatternWhyRead:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    snapshots, derived = await _pattern_sources(db)
    pattern = next(
        (item for item in derived if item.fingerprint == fingerprint), None
    )
    if pattern is None:
        raise HTTPException(status_code=404, detail="not_found")
    why = pattern_rules.explain_pattern(pattern, snapshots)
    if why is None:
        raise HTTPException(status_code=404, detail="not_found")
    return PatternWhyRead(
        pattern=_pattern_read(why.pattern),
        excerpts=[
            PatternWhyExcerptRead(
                session_id=item.session_id,
                completed_at=_utc_z(item.completed_at) or "",
                text=item.text,
            )
            for item in why.excerpts
        ],
    )


@router.post("/patterns/{fingerprint}/dismiss")
async def dismiss_readiness_pattern(
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not FINGERPRINT_RE.fullmatch(fingerprint):
        raise HTTPException(status_code=422, detail="invalid_input")
    if not settings.HATCH_COACH_READINESS_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    _snapshots, derived = await _pattern_sources(db)
    if not any(item.fingerprint == fingerprint for item in derived):
        raise HTTPException(status_code=404, detail="not_found")
    if await db.get(CoachPatternDismissal, fingerprint) is None:
        db.add(CoachPatternDismissal(fingerprint=fingerprint))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
    return {"fingerprint": fingerprint, "dismissed": True}


@router.delete("/patterns/{fingerprint}/dismiss")
async def undo_readiness_pattern_dismissal(
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await db.execute(
        delete(CoachPatternDismissal).where(
            CoachPatternDismissal.fingerprint == fingerprint
        )
    )
    await db.commit()
    return {"fingerprint": fingerprint, "dismissed": False}
