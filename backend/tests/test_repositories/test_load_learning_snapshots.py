"""Learning snapshot reads for pattern derivation (spec §7.1.6)."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models.coach_session import InterviewSession
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    ReportInputSnapshot,
    build_conversational_report,
)


def _report(session_id: str, key: str, level: str = "developing") -> dict:
    return build_conversational_report(
        ReportInputSnapshot(
            session_id=session_id,
            activity_version=1,
            retention_version=0,
            compatibility_key=key,
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
                    AcceptedAnswer(
                        f"answer-{session_id}-{root}",
                        {dimension: level for dimension in CONTENT_DIMENSIONS},
                    ),
                    (),
                )
                for root in (1, 2)
            ),
        )
    ).persisted_json()


def _session(
    session_id: str,
    key: str,
    completed_at: datetime,
    *,
    plan: dict | None = None,
    **overrides,
) -> InterviewSession:
    values = {
        "id": session_id,
        "company_name": "Synthetic Ltd",
        "role_title": "Engineer",
        "config": {},
        "status": "completed",
        "conversation_state": "completed",
        "experience_version": "conversational_v1",
        "completed_at": completed_at,
        "activity_version": 1,
        "report_state": "completed",
        "report_json": _report(session_id, key),
        "compatibility_key": key,
        "session_plan_json": plan
        or {
            "role": {"role_family": "software_engineering", "role_level": "senior"},
            "interview": {"type": "behavioural", "difficulty": "realistic"},
        },
    }
    values.update(overrides)
    return InterviewSession(**values)


@pytest.mark.asyncio
async def test_load_learning_snapshots_all_groups_and_unspecified_role(
    db_session,
) -> None:
    db_session.add_all(
        [
            _session("older", "key-older", datetime(2026, 1, 1)),
            _session(
                "newer",
                "key-newer",
                datetime(2026, 2, 1),
                plan={
                    "role": {"role_level": "senior"},
                    "interview": {"type": "behavioural", "difficulty": "challenging"},
                },
            ),
            _session(
                "active", "key-active", datetime(2026, 3, 1), status="active",
                conversation_state="asking",
            ),
        ]
    )
    await db_session.commit()

    snapshots = await ConversationalSessionRepository(db_session).load_learning_snapshots(
        limit=10
    )

    assert [item.session_id for item in snapshots] == ["newer", "older"]
    assert snapshots[0].role_family is None
    assert snapshots[0].difficulty == "challenging"
    assert snapshots[1].difficulty == "realistic"
    assert all(
        item.evaluation_contract_version == "coach_conversational_report_v1"
        for item in snapshots
    )


@pytest.mark.asyncio
async def test_load_learning_snapshots_excludes_sessions_being_deleted(
    db_session,
) -> None:
    db_session.add_all(
        [
            _session("visible", "key-visible", datetime(2026, 1, 1)),
            _session(
                "claimed", "key-claimed", datetime(2026, 2, 1),
                deletion_state="deleting",
            ),
            _session(
                "failed", "key-failed", datetime(2026, 3, 1),
                deletion_state="failed",
            ),
        ]
    )
    await db_session.commit()

    snapshots = await ConversationalSessionRepository(db_session).load_learning_snapshots()

    assert [item.session_id for item in snapshots] == ["visible"]
