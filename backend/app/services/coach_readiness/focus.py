"""Focus-area criteria and plan item auto-completion (spec §7.2, §7.3)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.services.coach_conversational_progress import ProgressSnapshot
from app.services.coach_conversational_report import LEVEL_TO_ORDINAL

from .contracts import (
    CriterionRead,
    CriterionStatus,
    FocusCriterion,
    FocusGroup,
    PlanItem,
)

LEVEL_TARGET = "interview_ready"
LEVEL_TARGET_RANK = LEVEL_TO_ORDINAL[LEVEL_TARGET]
PLAN_EXPIRY_DAYS = 14


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _group_of(area) -> FocusGroup | None:
    raw = getattr(area, "group_json", None)
    if not isinstance(raw, dict):
        return None
    role_family = raw.get("role_family")
    interview_type = raw.get("interview_type")
    if not isinstance(role_family, str) or not isinstance(interview_type, str):
        return None
    return FocusGroup(
        role_family=role_family,
        interview_type=interview_type,
        contract_version=str(
            raw.get("contract_version") or "coach_conversational_report_v1"
        ),
    )


def area_group(area) -> FocusGroup | None:
    return _group_of(area)


def area_criteria(area) -> tuple[FocusCriterion, ...]:
    criteria: list[FocusCriterion] = []
    for raw in getattr(area, "criteria_json", None) or ():
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        if kind not in {"level", "practice"}:
            continue
        count = 2 if kind == "level" else int(raw.get("count") or 1)
        criteria.append(FocusCriterion(kind=kind, count=count))
    return tuple(criteria)


def _same_group(snapshot: ProgressSnapshot, group: FocusGroup) -> bool:
    return (
        (snapshot.role_family or "unspecified") == group.role_family
        and (snapshot.interview_type or "unspecified") == group.interview_type
        and (snapshot.evaluation_contract_version or group.contract_version)
        == group.contract_version
    )


def _level_progress(
    area,
    criterion: FocusCriterion,
    snapshots: Sequence[ProgressSnapshot],
) -> tuple[int, CriterionStatus]:
    group = _group_of(area)
    if group is None:
        return 0, "no_evidence_yet"
    created = _utc(area.created_at)
    matching = [
        snapshot
        for snapshot in snapshots
        if _same_group(snapshot, group)
        and _utc(snapshot.completed_at) >= created
        and snapshot.dimensions.get(area.dimension) in LEVEL_TO_ORDINAL
        and snapshot.dimensions[area.dimension] != "not_assessed"
    ]
    met = [
        snapshot
        for snapshot in matching
        if LEVEL_TO_ORDINAL[snapshot.dimensions[area.dimension]] >= LEVEL_TARGET_RANK
    ]
    completed = min(len(met), criterion.count)
    if len(met) >= criterion.count:
        return completed, "met"
    if matching:
        return completed, "in_progress"
    return 0, "no_evidence_yet"


def _practice_progress(
    area, criterion: FocusCriterion, plans: Sequence[object]
) -> tuple[int, CriterionStatus]:
    completed = 0
    for plan in plans:
        if getattr(plan, "started_at", None) is None:
            continue
        for item in getattr(plan, "items_json", None) or ():
            if isinstance(item, dict) and item.get("status") == "done":
                completed += 1
    completed = min(completed, criterion.count)
    if completed >= criterion.count:
        return completed, "met"
    if completed > 0:
        return completed, "in_progress"
    return 0, "not_started"


def criterion_reads(
    area,
    snapshots: Sequence[ProgressSnapshot],
    plans: Sequence[object],
) -> tuple[CriterionRead, ...]:
    rows: list[CriterionRead] = []
    for criterion in area_criteria(area):
        if criterion.kind == "level":
            completed, status = _level_progress(area, criterion, snapshots)
            label = (
                f"Reach {LEVEL_TARGET} or better in {area.dimension.replace('_', ' ')} "
                f"in {criterion.count} practice sessions"
            )
        else:
            completed, status = _practice_progress(area, criterion, plans)
            label = f"Finish {criterion.count} plan items"
        rows.append(
            CriterionRead(
                kind=criterion.kind,
                label=label,
                status=status,
                completed=completed,
                target=criterion.count,
            )
        )
    return tuple(rows)


def all_criteria_met(
    area,
    snapshots: Sequence[ProgressSnapshot],
    plans: Sequence[object],
) -> bool:
    rows = criterion_reads(area, snapshots, plans)
    return bool(rows) and all(row.status == "met" for row in rows)


def lowest_free_slot(active_slots: Sequence[int | None]) -> int | None:
    used = {slot for slot in active_slots if slot in (1, 2, 3)}
    for slot in (1, 2, 3):
        if slot not in used:
            return slot
    return None


def apply_practice_completion(
    plan, snapshots: Sequence[ProgressSnapshot]
) -> bool:
    """Mark open practice items done when a later session in their group exists."""
    if getattr(plan, "started_at", None) is None:
        return False
    started = _utc(plan.started_at)
    changed = False
    items = []
    for item in getattr(plan, "items_json", None) or ():
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if (
            item.get("type") == "practice_session"
            and item.get("status") == "todo"
            and isinstance(item.get("group"), dict)
        ):
            group = item["group"]
            match = next(
                (
                    snapshot
                    for snapshot in snapshots
                    if (snapshot.role_family or "unspecified")
                    == group.get("role_family")
                    and (snapshot.interview_type or "unspecified")
                    == group.get("interview_type")
                    and (snapshot.evaluation_contract_version or "")
                    == group.get("contract_version", "")
                    and _utc(snapshot.completed_at) >= started
                ),
                None,
            )
            if match is not None:
                item["status"] = "done"
                item["auto"] = True
                item["completed_at"] = _utc(match.completed_at).isoformat()
                changed = True
        items.append(item)
    if changed:
        plan.items_json = items
        if all(
            item.get("status") in {"done", "skipped"} for item in items
        ):
            plan.status = "completed"
            plan.completed_at = datetime.utcnow()
    return changed


def plan_expired(plan, target_round, now: datetime) -> bool:
    if getattr(plan, "status", None) != "active":
        return False
    if getattr(plan, "started_at", None) is None:
        return False
    if _utc(now) >= _utc(plan.started_at) + timedelta(days=PLAN_EXPIRY_DAYS):
        return True
    return target_round is not None and _utc(target_round.scheduled_at) < _utc(now)


def plan_items(plan) -> tuple[PlanItem, ...]:
    items: list[PlanItem] = []
    for raw in getattr(plan, "items_json", None) or ():
        if not isinstance(raw, dict):
            continue
        items.append(
            PlanItem(
                id=str(raw.get("id") or ""),
                type=raw.get("type") or "practice_session",
                title=str(raw.get("title") or ""),
                minutes=int(raw.get("minutes") or 0),
                status=raw.get("status") or "todo",
                group=None,
                focus_area_ids=tuple(raw.get("focus_area_ids") or ()),
                auto=bool(raw.get("auto")),
                completed_at=(
                    datetime.fromisoformat(raw["completed_at"])
                    if isinstance(raw.get("completed_at"), str)
                    else None
                ),
            )
        )
    return tuple(items)
