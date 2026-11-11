"""Readiness writes bypass the AI setup gate (spec §4, §14; P4 review H2)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import main
from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_session import InterviewSession
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    ReportInputSnapshot,
    build_conversational_report,
)


def _report(session_id: str, key: str) -> dict:
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
                        {dimension: "needs_work" for dimension in CONTENT_DIMENSIONS},
                    ),
                    (),
                )
                for root in (1, 2)
            ),
        )
    ).persisted_json()


def _session(session_id: str, key: str, completed_at: datetime) -> InterviewSession:
    return InterviewSession(
        id=session_id,
        company_name="Synthetic Ltd",
        role_title="Delivery Lead",
        config={},
        status="completed",
        conversation_state="completed",
        experience_version="conversational_v1",
        completed_at=completed_at,
        activity_version=1,
        report_state="completed",
        report_json=_report(session_id, key),
        compatibility_key=key,
        session_plan_json={
            "role": {"role_family": "Delivery Lead", "role_level": "senior"},
            "interview": {"type": "behavioural", "difficulty": "realistic"},
        },
    )


@pytest.fixture(autouse=True)
def _readiness_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)
    # The AI setup feature gate is off for every test in this module.
    monkeypatch.setattr(main, "feature_enabled", lambda _name: False)


async def _seed_patterns(db: AsyncSession) -> None:
    now = datetime.utcnow()
    db.add_all(
        [
            _session("gate-1", "gate-key-1", now - timedelta(days=2)),
            _session("gate-2", "gate-key-2", now - timedelta(days=1)),
        ]
    )
    await db.commit()


@pytest.mark.asyncio
async def test_readiness_dismiss_and_undo_succeed_with_ai_gate_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_patterns(db_session)
    patterns = await client.get(
        "/api/coach/readiness/patterns", params={"include_stale": "true"}
    )
    fingerprint = patterns.json()["groups"][0]["patterns"][0]["fingerprint"]

    dismissed = await client.post(
        f"/api/coach/readiness/patterns/{fingerprint}/dismiss"
    )
    undone = await client.delete(
        f"/api/coach/readiness/patterns/{fingerprint}/dismiss"
    )

    assert dismissed.status_code == 200, dismissed.text
    assert undone.status_code == 200, undone.text


@pytest.mark.asyncio
async def test_readiness_debrief_save_succeeds_with_ai_gate_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(Application(id="gate-app", status="interview", priority="normal"))
    await db_session.flush()
    db_session.add(
        InterviewRound(
            id="gate-round",
            application_id="gate-app",
            round_number=1,
            type="behavioural",
            scheduled_at=(datetime.utcnow() - timedelta(hours=2)),
            duration_minutes=60,
            status="scheduled",
        )
    )
    await db_session.commit()

    response = await client.put(
        "/api/coach/readiness/rounds/gate-round/debrief",
        json={"expected_version": 0, "overall": 4, "questions": []},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "saved"


@pytest.mark.asyncio
async def test_non_readiness_coach_write_still_needs_ai_setup(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/coach/sessions", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "ai_setup_required"
