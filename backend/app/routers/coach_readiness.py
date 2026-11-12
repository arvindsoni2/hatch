"""Coach readiness coverage routes (P1)."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.application import InterviewRound
from ..models.question_bank import QuestionBankItem
from ..models.coach_readiness import (
    CoachFocusArea,
    CoachPatternDismissal,
    CoachPracticePlan,
)
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
    FocusAreaCreate,
    FocusAreaListRead,
    FocusAreaPatch,
    FocusAreaRead,
    FocusCriterionRead,
    FocusGroupRead,
    PlanCreate,
    PlanItemPatch,
    PlanItemRead,
    PlanListRead,
    PlanRead,
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
from ..services.coach_conversational_contracts import CONTENT_DIMENSIONS
from ..services.ai_setup import load_catalog, load_intent, load_probe_snapshot
from ..services.coach_readiness import coverage
from ..services.coach_readiness import focus as focus_rules
from ..services.coach_readiness import plan as plan_rules
from ..services.coach_readiness import patterns as pattern_rules
from ..services.coach_readiness.questions import likely_questions
from ..services.coach_readiness.contracts import (
    CoverageMap,
    CoverageOverride,
    CoverageOverview,
    DebriefQuestion,
    DebriefRead,
    PatternPolicy,
    PlanError,
    PlanFocusInput,
    PlanItem,
    ReadinessError,
    TargetRound,
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


def _focus_group_read(area) -> FocusGroupRead | None:
    group = focus_rules.area_group(area)
    if group is None:
        return None
    return FocusGroupRead(
        role_family=group.role_family,
        interview_type=group.interview_type,
        contract_version=group.contract_version,
    )


def _focus_read(area, snapshots, plans) -> FocusAreaRead:
    criteria = focus_rules.criterion_reads(area, snapshots, plans)
    return FocusAreaRead(
        id=area.id,
        version=area.version,
        status=area.status,
        active_slot=area.active_slot,
        title=area.title,
        dimension=area.dimension,
        group=_focus_group_read(area),
        application_id=area.application_id,
        criteria=[
            FocusCriterionRead(
                kind=row.kind,
                label=row.label,
                status=row.status,
                completed=row.completed,
                target=row.target,
            )
            for row in criteria
        ],
        every_criterion_met=bool(criteria)
        and all(row.status == "met" for row in criteria),
        created_at=_utc_z(area.created_at) or "",
    )


async def _focus_context(db: AsyncSession):
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    plans = (
        await db.execute(select(CoachPracticePlan))
    ).scalars().all()
    return snapshots, plans


@router.get("/focus-areas", response_model=FocusAreaListRead)
async def list_focus_areas(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FocusAreaListRead:
    snapshots, plans = await _focus_context(db)
    areas = (
        await db.execute(
            select(CoachFocusArea)
            .order_by(CoachFocusArea.created_at, CoachFocusArea.id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    active_count = await db.scalar(
        select(func.count()).select_from(CoachFocusArea).where(
            CoachFocusArea.status == "active"
        )
    )
    items = [_focus_read(area, snapshots, plans) for area in areas]
    return FocusAreaListRead(
        items=items, active_count=int(active_count or 0)
    )


def _parse_criteria(payload: FocusAreaCreate) -> list[dict]:
    criteria: list[dict] = []
    for item in payload.criteria:
        if item.kind == "level":
            if payload.group is None:
                raise HTTPException(status_code=422, detail="invalid_input")
            criteria.append({"kind": "level", "count": 2})
        else:
            criteria.append({"kind": "practice", "count": item.count or 3})
    return criteria


@router.post("/focus-areas", response_model=FocusAreaRead, status_code=201)
async def create_focus_area(
    payload: FocusAreaCreate,
    db: AsyncSession = Depends(get_db),
) -> FocusAreaRead:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    if payload.dimension not in CONTENT_DIMENSIONS:
        raise HTTPException(status_code=422, detail="invalid_input")
    criteria = _parse_criteria(payload)
    if payload.application_id is not None:
        from ..models.application import Application
        if await db.get(Application, payload.application_id) is None:
            raise HTTPException(status_code=404, detail="not_found")
    group = payload.group.model_dump() if payload.group is not None else None

    for _attempt in range(2):
        slots = (
            await db.execute(
                select(CoachFocusArea.active_slot).where(
                    CoachFocusArea.status == "active"
                )
            )
        ).scalars().all()
        slot = focus_rules.lowest_free_slot(slots)
        if slot is None:
            raise HTTPException(status_code=409, detail="limit_reached")
        area = CoachFocusArea(
            title=payload.title,
            dimension=payload.dimension,
            group_json=group,
            application_id=payload.application_id,
            criteria_json=criteria,
            status="active",
            active_slot=slot,
        )
        db.add(area)
        try:
            await db.commit()
            snapshots, plans = await _focus_context(db)
            return _focus_read(area, snapshots, plans)
        except IntegrityError:
            await db.rollback()
    raise HTTPException(status_code=409, detail="limit_reached")


_TRANSITIONS = {
    "active": {"active", "paused", "achieved", "archived"},
    "paused": {"paused", "active", "archived"},
    "achieved": {"achieved", "active"},
    "archived": set(),
}


@router.patch("/focus-areas/{area_id}", response_model=FocusAreaRead)
async def patch_focus_area(
    area_id: str,
    payload: FocusAreaPatch,
    db: AsyncSession = Depends(get_db),
) -> FocusAreaRead:
    area = await db.get(CoachFocusArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="not_found")
    if area.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="version_conflict")
    target_status = payload.status or area.status
    if target_status not in _TRANSITIONS[area.status]:
        raise HTTPException(status_code=409, detail="invalid_state")

    # The versioned UPDATE is the transaction's first write and takes SQLite's
    # write lock before active-slot allocation.
    result = await db.execute(
        update(CoachFocusArea)
        .where(
            CoachFocusArea.id == area_id,
            CoachFocusArea.version == payload.expected_version,
        )
        .values(version=CoachFocusArea.version + 1)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="version_conflict")
    area = await db.get(CoachFocusArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="not_found")

    if payload.title is not None:
        area.title = payload.title
    if target_status != area.status:
        if target_status == "active":
            slots = (
                await db.execute(
                    select(CoachFocusArea.active_slot).where(
                        CoachFocusArea.status == "active",
                        CoachFocusArea.id != area_id,
                    )
                )
            ).scalars().all()
            slot = focus_rules.lowest_free_slot(slots)
            if slot is None:
                await db.rollback()
                raise HTTPException(status_code=409, detail="limit_reached")
            area.active_slot = slot
        else:
            area.active_slot = None
        area.status = target_status
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="limit_reached")
    snapshots, plans = await _focus_context(db)
    return _focus_read(area, snapshots, plans)


def _plan_item_json(item: PlanItem) -> dict:
    return {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "minutes": item.minutes,
        "status": item.status,
        "group": (
            {
                "role_family": item.group.role_family,
                "interview_type": item.group.interview_type,
                "contract_version": item.group.contract_version,
            }
            if item.group is not None
            else None
        ),
        "difficulty": item.difficulty,
        "focus_area_ids": list(item.focus_area_ids),
        "due_at": _utc_z(item.due_at),
        "story_competency": item.story_competency,
        "question_id": item.question_id,
        "auto": item.auto,
        "completed_at": _utc_z(item.completed_at),
    }


def _plan_read(plan) -> PlanRead:
    items = [item for item in (plan.items_json or ()) if isinstance(item, dict)]
    done = sum(item.get("status") == "done" for item in items)
    allocated = sum(int(item.get("minutes") or 0) for item in items)
    return PlanRead(
        id=plan.id,
        version=plan.version,
        status=plan.status,
        minutes=plan.minutes,
        target_round_id=plan.target_round_id,
        items=[
            PlanItemRead(
                id=str(item.get("id") or ""),
                type=item.get("type") or "practice_session",
                title=str(item.get("title") or ""),
                minutes=int(item.get("minutes") or 0),
                status=item.get("status") or "todo",
                group=(
                    FocusGroupRead(**item["group"])
                    if isinstance(item.get("group"), dict)
                    else None
                ),
                difficulty=item.get("difficulty"),
                focus_area_ids=list(item.get("focus_area_ids") or ()),
                due_at=item.get("due_at"),
                story_competency=item.get("story_competency"),
                question_id=item.get("question_id"),
                auto=bool(item.get("auto")),
                completed_at=item.get("completed_at"),
            )
            for item in items
        ],
        unallocated_minutes=max(0, plan.minutes - allocated),
        done_count=done,
        total_count=len(items),
        started_at=_utc_z(plan.started_at),
        completed_at=_utc_z(plan.completed_at),
    )


async def _target_round(db: AsyncSession, round_id: str | None):
    if not round_id:
        return None
    round_row = await db.get(InterviewRound, round_id)
    if round_row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return round_row


def _target(round_row) -> TargetRound | None:
    if round_row is None or round_row.scheduled_at is None:
        return None
    return TargetRound(
        round_id=round_row.id,
        scheduled_at=round_row.scheduled_at,
        application_id=round_row.application_id,
    )


async def _plan_context(db: AsyncSession, round_row):
    snapshots, plans = await _focus_context(db)
    active_areas = (
        await db.execute(
            select(CoachFocusArea).where(CoachFocusArea.status == "active")
        )
    ).scalars().all()
    latest: dict[tuple[str, str, str], tuple[datetime, str]] = {}
    for snapshot in snapshots:
        if not snapshot.difficulty:
            continue
        key = (
            snapshot.role_family or "unspecified",
            snapshot.interview_type or "unspecified",
            snapshot.evaluation_contract_version,
        )
        if key not in latest or snapshot.completed_at > latest[key][0]:
            latest[key] = (snapshot.completed_at, snapshot.difficulty)
    focus_inputs = []
    for area in active_areas:
        group = focus_rules.area_group(area)
        difficulty = None
        if group is not None:
            difficulty = latest.get(
                (group.role_family, group.interview_type, group.contract_version),
                (None, None),
            )[1]
        focus_inputs.append(
            PlanFocusInput(
                focus_id=area.id,
                title=area.title,
                status=area.status,
                group=group,
                created_at=area.created_at,
                all_criteria_met=focus_rules.all_criteria_met(area, snapshots, plans),
                latest_difficulty=difficulty,
            )
        )
    gaps: list[str] = []
    question: str | None = None
    if round_row is not None and round_row.application_id:
        coverage_map = await coverage.coverage_for_application(
            db, round_row.application_id
        )
        if coverage_map is not None:
            gaps = [
                item.competency
                for item in coverage_map.competencies
                if item.status == "gap"
            ]
        questions = await likely_questions(db, round_row.application_id)
        question = None
        question_id = None
        for candidate in questions:
            reference = candidate.source_ref or {}
            if reference.get("kind") == "question_bank_item":
                item = await db.get(QuestionBankItem, reference["id"])
                if item is not None and (item.answer_draft or "").strip():
                    continue
                question_id = reference["id"]
            question = candidate.text
            break
    else:
        question_id = None
    return focus_inputs, gaps, question, question_id


@router.get("/plans", response_model=PlanListRead)
async def list_plans(db: AsyncSession = Depends(get_db)) -> PlanListRead:
    rows = (
        await db.execute(
            select(CoachPracticePlan)
            .where(CoachPracticePlan.status.in_(("active", "draft")))
            .order_by(CoachPracticePlan.created_at.desc())
        )
    ).scalars().all()
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    active = None
    draft = None
    changed = False
    for plan in rows:
        if plan.status == "active":
            changed = focus_rules.apply_practice_completion(plan, snapshots) or changed
            round_row = (
                await db.get(InterviewRound, plan.target_round_id)
                if plan.target_round_id
                else None
            )
            if focus_rules.plan_expired(plan, _target(round_row), datetime.now(UTC)):
                plan.status = "expired"
                plan.version += 1
                changed = True
            if plan.status == "active":
                active = _plan_read(plan)
        elif plan.status == "draft" and draft is None:
            draft = _plan_read(plan)
    if changed:
        await db.commit()
    return PlanListRead(active=active, draft=draft)


@router.post("/plans", response_model=PlanRead, status_code=201)
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_db),
) -> PlanRead:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    round_row = await _target_round(db, payload.target_round_id)
    focus_inputs, gaps, question, question_id = await _plan_context(db, round_row)
    try:
        draft = plan_rules.build_plan(
            focus_areas=focus_inputs,
            target_round=_target(round_row),
            minutes=payload.minutes,
            now=datetime.now(UTC),
            coverage_gaps=gaps,
            likely_question=question,
            likely_question_id=question_id,
        )
    except PlanError as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    plan = CoachPracticePlan(
        status="draft",
        minutes=payload.minutes,
        target_round_id=payload.target_round_id,
        items_json=[_plan_item_json(item) for item in draft.items],
    )
    db.add(plan)
    await db.commit()
    return _plan_read(plan)


@router.post("/plans/{plan_id}/start", response_model=PlanRead)
async def start_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlanRead:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        raise HTTPException(status_code=403, detail="disabled")
    plan = await db.get(CoachPracticePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="not_found")
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="invalid_state")
    await db.execute(
        update(CoachPracticePlan)
        .where(CoachPracticePlan.status == "active")
        .values(status="superseded", version=CoachPracticePlan.version + 1)
    )
    plan.status = "active"
    plan.started_at = datetime.utcnow()
    plan.version += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="invalid_state")
    return _plan_read(plan)


@router.patch("/plans/{plan_id}/items/{item_id}", response_model=PlanRead)
async def patch_plan_item(
    plan_id: str,
    item_id: str,
    payload: PlanItemPatch,
    db: AsyncSession = Depends(get_db),
) -> PlanRead:
    plan = await db.get(CoachPracticePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="not_found")
    if plan.status != "active":
        raise HTTPException(status_code=409, detail="invalid_state")
    result = await db.execute(
        update(CoachPracticePlan)
        .where(
            CoachPracticePlan.id == plan_id,
            CoachPracticePlan.version == payload.expected_version,
        )
        .values(version=CoachPracticePlan.version + 1)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="version_conflict")
    plan = await db.get(CoachPracticePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="not_found")
    plan.version = payload.expected_version + 1
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    focus_rules.apply_practice_completion(plan, snapshots)
    round_row = (
        await db.get(InterviewRound, plan.target_round_id)
        if plan.target_round_id
        else None
    )
    if focus_rules.plan_expired(plan, _target(round_row), datetime.now(UTC)):
        plan.status = "expired"
        await db.commit()
        raise HTTPException(status_code=409, detail="invalid_state")
    items = [dict(item) for item in (plan.items_json or ()) if isinstance(item, dict)]
    item = next((row for row in items if row.get("id") == item_id), None)
    if item is None:
        await db.rollback()
        raise HTTPException(status_code=404, detail="not_found")
    if payload.action == "done" and item.get("status") == "done":
        pass
    elif payload.action == "done" and item.get("status") == "todo":
        item["status"] = "done"
        item["auto"] = False
        item["completed_at"] = datetime.utcnow().isoformat()
    elif payload.action == "skipped" and item.get("status") in {"todo", "skipped"}:
        item["status"] = "skipped"
    elif payload.action == "todo" and item.get("status") == "skipped":
        item["status"] = "todo"
    elif payload.action == "todo" and item.get("status") == "done" and not item.get("auto"):
        item["status"] = "todo"
        item["completed_at"] = None
    else:
        await db.rollback()
        raise HTTPException(status_code=409, detail="invalid_state")
    plan.items_json = items
    if all(row.get("status") in {"done", "skipped"} for row in items):
        plan.status = "completed"
        plan.completed_at = datetime.utcnow()
    await db.commit()
    return _plan_read(plan)
