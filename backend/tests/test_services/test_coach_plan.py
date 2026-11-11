"""Deterministic plan building and expiry (spec §7.3, §8.3)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.coach_readiness import focus as focus_rules
from app.services.coach_readiness import plan as plan_rules
from app.services.coach_readiness.contracts import (
    FocusGroup,
    PlanError,
    PlanFocusInput,
    TargetRound,
)

NOW = datetime(2026, 5, 1, 12, 0)
GROUP_A = FocusGroup("Delivery Lead", "behavioural")
GROUP_B = FocusGroup("Data", "behavioural")


def _focus(
    focus_id: str,
    group: FocusGroup | None,
    *,
    created_at: datetime = NOW,
    met: bool = False,
) -> PlanFocusInput:
    return PlanFocusInput(
        focus_id=focus_id,
        title=f"Focus {focus_id}",
        status="active",
        group=group,
        created_at=created_at,
        all_criteria_met=met,
    )


def test_plan_fits_whole_items_and_reports_unallocated() -> None:
    draft = plan_rules.build_plan(
        focus_areas=[_focus("a", GROUP_A), _focus("b", GROUP_B), _focus("c", None)],
        target_round=None,
        minutes=25,
        now=NOW,
    )

    assert [item.minutes for item in draft.items] == [15]
    assert draft.unallocated_minutes == 10
    assert sum(item.minutes for item in draft.items) <= 25


def test_focus_areas_in_one_group_share_one_practice_item() -> None:
    draft = plan_rules.build_plan(
        focus_areas=[
            _focus("a", GROUP_A),
            _focus("b", GROUP_A),
        ],
        target_round=None,
        minutes=30,
        now=NOW,
    )

    practice = [item for item in draft.items if item.type == "practice_session"]
    assert len(practice) == 1
    assert practice[0].focus_area_ids == ("a", "b")


def test_met_focus_areas_skipped() -> None:
    draft = plan_rules.build_plan(
        focus_areas=[_focus("done", GROUP_A, met=True), _focus("open", GROUP_B)],
        target_round=None,
        minutes=30,
        now=NOW,
    )

    assert [item.focus_area_ids for item in draft.items] == [("open",)]


def test_round_within_seven_days_orders_story_review_story_practice() -> None:
    target = TargetRound(
        round_id="round-1", scheduled_at=NOW + timedelta(days=5)
    )
    draft = plan_rules.build_plan(
        focus_areas=[_focus("a", GROUP_A)],
        target_round=target,
        minutes=50,
        now=NOW,
        coverage_gaps=["budget ownership", "stakeholder management"],
        likely_question="Tell me about a delivery that slipped.",
    )

    assert [item.type for item in draft.items] == [
        "story_work", "review_answer", "story_work", "practice_session"
    ]
    assert draft.unallocated_minutes == 10


def test_plan_due_at_round_minus_two_hours() -> None:
    target = TargetRound(
        round_id="round-1", scheduled_at=NOW + timedelta(days=3)
    )
    draft = plan_rules.build_plan(
        focus_areas=[_focus("a", GROUP_A)],
        target_round=target,
        minutes=30,
        now=NOW,
    )

    assert {item.due_at.replace(tzinfo=None) for item in draft.items} == {
        target.scheduled_at - timedelta(hours=2)
    }


def test_round_under_two_hours_is_invalid_input() -> None:
    target = TargetRound(
        round_id="round-1", scheduled_at=NOW + timedelta(minutes=90)
    )
    with pytest.raises(PlanError) as invalid:
        plan_rules.build_plan(
            focus_areas=[_focus("a", GROUP_A)],
            target_round=target,
            minutes=30,
            now=NOW,
        )
    assert invalid.value.code == "invalid_input"


def test_one_session_completes_every_open_practice_item_in_group() -> None:
    plan = type(
        "Plan",
        (),
        {
            "status": "active",
            "started_at": NOW - timedelta(days=1),
            "items_json": [
                {
                    "id": "a", "type": "practice_session", "status": "todo",
                    "group": {
                        "role_family": "Delivery Lead",
                        "interview_type": "behavioural",
                        "contract_version": "coach_conversational_report_v1",
                    },
                },
                {
                    "id": "b", "type": "practice_session", "status": "todo",
                    "group": {
                        "role_family": "Delivery Lead",
                        "interview_type": "behavioural",
                        "contract_version": "coach_conversational_report_v1",
                    },
                },
                {
                    "id": "c", "type": "practice_session", "status": "todo",
                    "group": {
                        "role_family": "Data",
                        "interview_type": "behavioural",
                        "contract_version": "coach_conversational_report_v1",
                    },
                },
            ],
            "completed_at": None,
        },
    )()
    snapshot = type(
        "Snapshot",
        (),
        {
            "role_family": "Delivery Lead",
            "interview_type": "behavioural",
            "evaluation_contract_version": "coach_conversational_report_v1",
            "completed_at": NOW,
        },
    )()

    focus_rules.apply_practice_completion(plan, [snapshot])

    assert [item["status"] for item in plan.items_json] == ["done", "done", "todo"]
    assert plan.items_json[0]["auto"] is True


def test_plan_expiry_after_14_days_or_round_passed() -> None:
    active = type(
        "Plan", (), {"status": "active", "started_at": NOW - timedelta(days=15)}
    )()
    recent = type(
        "Plan", (), {"status": "active", "started_at": NOW - timedelta(days=13)}
    )()
    passed = TargetRound(
        round_id="round-1", scheduled_at=NOW - timedelta(hours=1)
    )

    assert focus_rules.plan_expired(active, None, NOW) is True
    assert focus_rules.plan_expired(recent, None, NOW) is False
    assert focus_rules.plan_expired(recent, passed, NOW) is True
