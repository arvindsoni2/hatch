"""Brief skeleton, state and archive contracts (spec §7.5, §8.4)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachDerivedText, CoachInterviewBrief
from app.models.coach_session import InterviewSession
from app.models.job import JobPosting
from app.models.story import Story
from app.services.coach_conversational_progress import ProgressSnapshot
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    ReportInputSnapshot,
    build_conversational_report,
)
from app.services.coach_readiness import brief as brief_service
from app.services.coach_readiness.next_actions import debrief_next_actions


@pytest.fixture(autouse=True)
def _brief_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)


async def _seed(db, *, round_type="behavioural", scheduled_at=None, status="scheduled"):
    db.add(Application(id="brief-app", job_id="brief-job", status="interview", priority="normal"))
    db.add(JobPosting(
        id="brief-job", title="Delivery Lead", company="Northwind", url="https://example.test/brief",
        source="synthetic", description="Lead delivery of the billing platform.",
    ))
    db.add(InterviewRound(
        id="brief-round", application_id="brief-app", round_number=1,
        type=round_type, scheduled_at=scheduled_at or datetime(2026, 12, 20, 10, 0),
        duration_minutes=60, status=status, interviewer_name="Priya", location="Video call",
    ))
    db.add(Story(
        id="brief-story", title="Rescued a late delivery", slug="brief-story",
        situation="Synthetic situation", task="Synthetic task", action="Synthetic action",
        result="Delivered on time", tags=["delivery"], skills=["delivery"], metrics=["2 weeks"],
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_brief_ready_with_ai_off_all_sections(db_session) -> None:
    await _seed(db_session)

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data is not None
    assert data["state"] == "active"
    assert set(data) >= {
        "header", "likely_questions", "stories", "watch_outs", "gaps",
        "ask_them", "enhancement",
    }
    assert data["header"]["company"] == "Northwind"
    assert data["enhancement"]["state"] == "none"


@pytest.mark.asyncio
async def test_section_limits_and_source_order(db_session) -> None:
    await _seed(db_session)

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert len(data["likely_questions"]) <= 5
    assert len(data["stories"]) <= 3
    assert len(data["watch_outs"]) <= 2
    assert len(data["gaps"]) <= 2
    assert len(data["ask_them"]) <= 3


def _learning_session(
    session_id: str, interview_type: str, dimension: str, completed_at: datetime
) -> InterviewSession:
    report = build_conversational_report(
        ReportInputSnapshot(
            session_id=session_id,
            activity_version=1,
            retention_version=0,
            compatibility_key=f"key-{session_id}",
            counts={
                "planned_questions_total": 2,
                "planned_questions_answered": 2,
                "planned_questions_skipped": 0,
                "follow_ups_asked": 0,
                "follow_ups_answered": 0,
                "accepted_attempts": 2,
                "retry_attempts": 0,
                "unavailable_attempts": 0,
                "hints_used": 0,
            },
            accepted_root_bundles=tuple(
                (
                    AcceptedAnswer(f"answer-{session_id}-{root}", {dimension: "needs_work"}),
                    (),
                )
                for root in (1, 2)
            ),
        )
    )
    return InterviewSession(
        id=session_id,
        application_id="brief-app",
        company_name="Northwind",
        role_title="Delivery Lead",
        config={},
        status="completed",
        conversation_state="completed",
        experience_version="conversational_v1",
        completed_at=completed_at,
        activity_version=1,
        report_state="completed",
        report_json=report.persisted_json(),
        compatibility_key=f"key-{session_id}",
        session_plan_json={
            "role": {"role_family": "Delivery Lead", "role_level": "senior"},
            "interview": {"type": interview_type, "difficulty": "realistic"},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("round_type", "expected", "excluded"),
    [
        ("technical", {"structure"}, {"specificity"}),
        ("phone_screen", {"specificity", "structure"}, set()),
    ],
)
async def test_round_type_maps_to_practice_interview_types(
    db_session, round_type, expected, excluded
) -> None:
    await _seed(db_session, round_type=round_type)
    db_session.add_all(
        [
            _learning_session(
                f"behavioural-{index}", "behavioural", "specificity",
                datetime(2026, 11, index),
            )
            for index in (10, 11)
        ]
        + [
            _learning_session(
                f"role-specific-{index}", "role_specific_verbal", "structure",
                datetime(2026, 11, index),
            )
            for index in (12, 13)
        ]
    )
    await db_session.commit()

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data is not None
    assert data["header"]["round_type"] == round_type
    dimensions = {item["dimension"] for item in data["watch_outs"]}
    assert expected <= dimensions
    assert not (excluded & dimensions)
    assert brief_service.PRACTICE_TYPES == {
        "behavioural": ("behavioural", "mixed"),
        "culture_fit": ("behavioural", "mixed"),
        "technical": ("role_specific_verbal", "mixed"),
        "assessment": ("role_specific_verbal", "mixed"),
        "presentation": ("role_specific_verbal", "mixed"),
        "phone_screen": ("behavioural", "role_specific_verbal", "mixed"),
        "panel": ("behavioural", "role_specific_verbal", "mixed"),
        "final": ("behavioural", "role_specific_verbal", "mixed"),
    }


def test_role_family_from_latest_linked_session() -> None:
    snapshots = [
        ProgressSnapshot(
            session_id="old", compatibility_key="k", activity_version=1,
            completed_at=datetime(2026, 1, 1), session_level="developing",
            dimensions={}, application_id="app", role_family="Data",
        ),
        ProgressSnapshot(
            session_id="new", compatibility_key="k", activity_version=1,
            completed_at=datetime(2026, 2, 1), session_level="developing",
            dimensions={}, application_id="app", role_family="Delivery Lead",
        ),
    ]
    assert brief_service._role_family(snapshots, "app") == "Delivery Lead"
    assert brief_service._role_family([], "app") is None


@pytest.mark.asyncio
async def test_skeleton_reflects_edits_on_next_read(db_session) -> None:
    await _seed(db_session)
    before = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )
    job = await db_session.get(JobPosting, "brief-job")
    job.title = "Principal Delivery Lead"
    await db_session.commit()

    after = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert before["header"]["role"] == "Delivery Lead"
    assert after["header"]["role"] == "Principal Delivery Lead"


@pytest.mark.asyncio
async def test_fingerprint_mismatch_reads_outdated(db_session) -> None:
    await _seed(db_session)
    text = CoachDerivedText(
        id="brief-text", kind="brief", cache_key="brief-cache",
        text_json={"talking_points": []}, model_identity="m", prompt_version="v1",
        created_at=datetime(2026, 1, 1),
    )
    db_session.add(text)
    db_session.add(CoachInterviewBrief(
        id="brief-row", interview_round_id="brief-round",
        enhancement_state="current", enhancement_fingerprint="old", enhanced_text_id="brief-text",
    ))
    await db_session.commit()

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data["enhancement"]["state"] == "outdated"


@pytest.mark.asyncio
async def test_purged_text_reads_as_none(db_session) -> None:
    await _seed(db_session)
    db_session.add(CoachInterviewBrief(
        id="brief-row", interview_round_id="brief-round",
        enhancement_state="current", enhancement_fingerprint="old", enhanced_text_id=None,
    ))
    await db_session.commit()

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data["enhancement"]["state"] == "none"


@pytest.mark.asyncio
async def test_brief_next_actions_for_upcoming_and_missing_round(db_session) -> None:
    now = datetime.utcnow()
    await _seed(db_session, scheduled_at=now + timedelta(days=3))
    db_session.add_all([
        Application(id="brief-app-no-round", status="interview", priority="normal"),
        Application(id="brief-app-later", status="interview", priority="normal"),
        InterviewRound(
            id="brief-later-round", application_id="brief-app-later", round_number=1,
            type="behavioural", scheduled_at=now + timedelta(days=20), status="scheduled",
        ),
    ])
    await db_session.commit()

    actions = [item for item in await debrief_next_actions(db_session, now) if item["kind"] == "brief"]

    assert {item["application_id"] for item in actions} == {
        "brief-app", "brief-app-no-round",
    }
    assert any(item["round_id"] == "brief-round" and "brief ready" in item["action"] for item in actions)
    assert any(item["application_id"] == "brief-app-no-round" and item["round_id"] == "" for item in actions)


@pytest.mark.asyncio
async def test_enhancing_row_reads_enhancing(db_session) -> None:
    await _seed(db_session)
    db_session.add(CoachInterviewBrief(
        id="brief-row", interview_round_id="brief-round",
        enhancement_state="enhancing", enhanced_text_id=None,
    ))
    await db_session.commit()

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data["enhancement"]["state"] == "enhancing"


@pytest.mark.asyncio
async def test_brief_archives_after_round_time_or_completed(db_session) -> None:
    await _seed(db_session, scheduled_at=datetime(2026, 1, 1, 10, 0))

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 2, 1, tzinfo=None)
    )
    assert data["state"] == "archived"


@pytest.mark.asyncio
async def test_cancelled_round_archives_brief(db_session) -> None:
    await _seed(db_session, status="cancelled")

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )
    assert data["state"] == "archived"


@pytest.mark.asyncio
async def test_brief_without_round_date(db_session) -> None:
    await _seed(db_session, scheduled_at=None)
    round_row = await db_session.get(InterviewRound, "brief-round")
    round_row.scheduled_at = None
    await db_session.commit()

    data = await brief_service.build_brief(
        db_session, "brief-round", datetime(2026, 12, 1, tzinfo=None)
    )

    assert data is not None
    assert data["header"]["starts_at"] is None
    assert data["state"] == "active"
