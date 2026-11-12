"""Deterministic, time-boxed practice-plan builder (spec §7.3)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from .contracts import (
    FocusGroup,
    PlanDraft,
    PlanError,
    PlanFocusInput,
    PlanItem,
    TargetRound,
)

MAX_ITEMS = 6
PRACTICE_MINUTES = 15
STORY_MINUTES = 10
REVIEW_MINUTES = 5
PLAN_LEAD_TIME = timedelta(hours=2)
NEAR_ROUND = timedelta(days=7)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _practice_title(group: FocusGroup) -> str:
    interview_type = group.interview_type.replace("_", " ")
    return f"Practise a {interview_type} session — {group.role_family}"


def _group_key(group: FocusGroup) -> tuple[str, str, str]:
    return group.role_family, group.interview_type, group.contract_version


def build_plan(
    *,
    focus_areas: Sequence[PlanFocusInput],
    target_round: TargetRound | None,
    minutes: int,
    now: datetime,
    coverage_gaps: Sequence[str] = (),
    likely_question: str | None = None,
    likely_question_id: str | None = None,
) -> PlanDraft:
    if not 10 <= minutes <= 120:
        raise PlanError("invalid_input")
    if target_round is not None:
        lead = _utc(target_round.scheduled_at) - _utc(now)
        if lead < PLAN_LEAD_TIME:
            raise PlanError("invalid_input")

    due_at = None
    if target_round is not None:
        due_at = _utc(target_round.scheduled_at) - PLAN_LEAD_TIME

    eligible = [
        area
        for area in focus_areas
        if area.status == "active" and not area.all_criteria_met
    ]
    grouped: dict[tuple[str, str, str], list[PlanFocusInput]] = {}
    for area in eligible:
        if area.group is None:
            continue
        grouped.setdefault(_group_key(area.group), []).append(area)

    practice_items: list[PlanItem] = []
    for key in sorted(
        grouped,
        key=lambda value: (
            min(area.created_at for area in grouped[value]),
            value,
        ),
    ):
        members = sorted(grouped[key], key=lambda area: (area.created_at, area.focus_id))
        group = members[0].group
        assert group is not None
        practice_items.append(
            PlanItem(
                id="",
                type="practice_session",
                title=_practice_title(group),
                minutes=PRACTICE_MINUTES,
                group=group,
                difficulty=members[0].latest_difficulty or "realistic",
                due_at=due_at,
                focus_area_ids=tuple(area.focus_id for area in members),
            )
        )

    story_items = [
        PlanItem(
            id="",
            type="story_work",
            title=f"Draft a story for {competency}",
            minutes=STORY_MINUTES,
            story_competency=competency,
            due_at=due_at,
        )
        for competency in list(coverage_gaps)[:2]
    ]
    review_item = (
        PlanItem(
            id="",
            type="review_answer",
            title=f'Re-read your answer to "{likely_question}"',
            minutes=REVIEW_MINUTES,
            due_at=due_at,
            question_id=likely_question_id,
        )
        if likely_question
        else None
    )

    near_round = (
        target_round is not None
        and _utc(target_round.scheduled_at) - _utc(now) < NEAR_ROUND
    )
    if near_round:
        candidates: list[PlanItem] = []
        if story_items:
            candidates.append(story_items[0])
        if review_item is not None:
            candidates.append(review_item)
        if len(story_items) > 1:
            candidates.append(story_items[1])
        candidates.extend(practice_items)
    else:
        candidates = list(practice_items)
        if target_round is not None:
            candidates.extend(story_items)
            if review_item is not None:
                candidates.append(review_item)

    items: list[PlanItem] = []
    remaining = minutes
    for item in candidates:
        if len(items) >= MAX_ITEMS:
            break
        if item.minutes > remaining:
            continue
        items.append(
            PlanItem(
                id=f"item-{len(items) + 1}",
                type=item.type,
                title=item.title,
                minutes=item.minutes,
                group=item.group,
                difficulty=item.difficulty,
                focus_area_ids=item.focus_area_ids,
                due_at=item.due_at,
                story_competency=item.story_competency,
                question_id=item.question_id,
            )
        )
        remaining -= item.minutes
    return PlanDraft(items=tuple(items), unallocated_minutes=remaining)
