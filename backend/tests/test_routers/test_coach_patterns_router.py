"""Readiness pattern routes (spec §12)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import settings
from app.models.coach_readiness import CoachPatternDismissal
from app.models.coach_session import InterviewSession
from app.routers.coach_readiness import (
    dismiss_readiness_pattern,
    get_readiness_pattern_why,
    get_readiness_patterns,
    undo_readiness_pattern_dismissal,
)
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
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)


async def _seed(db_session) -> None:
    db_session.add_all(
        [
            _session("s1", "key-1", datetime.utcnow() - timedelta(days=2)),
            _session("s2", "key-2", datetime.utcnow() - timedelta(days=1)),
        ]
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_patterns_group_and_why_read_deterministically(db_session) -> None:
    await _seed(db_session)

    payload = await get_readiness_patterns(
        group=None, include_stale=True, db=db_session
    )

    assert len(payload.groups) == 1
    group = payload.groups[0]
    assert group.role_family == "Delivery Lead"
    assert group.interview_type == "behavioural"
    assert group.session_count == 2
    pattern = next(item for item in group.patterns if item.dimension == "specificity")
    assert pattern.kind == "focus"
    assert [item.session_id for item in pattern.supporting] == ["s1", "s2"]
    assert pattern.dismissed is False

    why = await get_readiness_pattern_why(
        pattern.fingerprint, db=db_session
    )
    assert why.pattern.fingerprint == pattern.fingerprint


@pytest.mark.asyncio
async def test_dismiss_and_undo_round_trip(db_session) -> None:
    await _seed(db_session)
    payload = await get_readiness_patterns(group=None, include_stale=True, db=db_session)
    fingerprint = payload.groups[0].patterns[0].fingerprint

    dismissed = await dismiss_readiness_pattern(fingerprint, db=db_session)
    assert dismissed == {"fingerprint": fingerprint, "dismissed": True}
    after = await get_readiness_patterns(group=None, include_stale=True, db=db_session)
    assert next(
        item for item in after.groups[0].patterns if item.fingerprint == fingerprint
    ).dismissed is True

    undone = await undo_readiness_pattern_dismissal(fingerprint, db=db_session)
    assert undone == {"fingerprint": fingerprint, "dismissed": False}
    restored = await get_readiness_patterns(group=None, include_stale=True, db=db_session)
    assert next(
        item for item in restored.groups[0].patterns if item.fingerprint == fingerprint
    ).dismissed is False


@pytest.mark.asyncio
async def test_flag_off_returns_no_patterns(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(db_session)
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", False)

    payload = await get_readiness_patterns(group=None, include_stale=True, db=db_session)

    assert payload.groups == []


@pytest.mark.asyncio
async def test_dismiss_rejects_invalid_fingerprint(db_session) -> None:
    with pytest.raises(HTTPException) as invalid:
        await dismiss_readiness_pattern("not-a-fingerprint", db=db_session)

    assert invalid.value.status_code == 422
    assert invalid.value.detail == "invalid_input"


@pytest.mark.asyncio
async def test_dismiss_unknown_fingerprint_returns_not_found(db_session) -> None:
    await _seed(db_session)

    with pytest.raises(HTTPException) as missing:
        await dismiss_readiness_pattern("0" * 64, db=db_session)

    assert missing.value.status_code == 404
    assert missing.value.detail == "not_found"


@pytest.mark.asyncio
async def test_dismiss_is_idempotent(db_session) -> None:
    await _seed(db_session)
    payload = await get_readiness_patterns(group=None, include_stale=True, db=db_session)
    fingerprint = payload.groups[0].patterns[0].fingerprint

    first = await dismiss_readiness_pattern(fingerprint, db=db_session)
    second = await dismiss_readiness_pattern(fingerprint, db=db_session)

    assert first == second == {"fingerprint": fingerprint, "dismissed": True}
    count = await db_session.scalar(
        select(func.count()).select_from(CoachPatternDismissal)
    )
    assert count == 1


@pytest.mark.asyncio
async def test_why_flag_off_returns_disabled(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(db_session)
    payload = await get_readiness_patterns(group=None, include_stale=True, db=db_session)
    fingerprint = payload.groups[0].patterns[0].fingerprint
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", False)

    with pytest.raises(HTTPException) as disabled:
        await get_readiness_pattern_why(fingerprint, db=db_session)

    assert disabled.value.status_code == 403
    assert disabled.value.detail == "disabled"
