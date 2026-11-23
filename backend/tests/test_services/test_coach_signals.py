"""Real-interview signals derived on read from saved debriefs (spec §7.1.5).

Signals are pure derivation: nothing is stored, they never feed
``derive_patterns``, and a key needs N ≥ 2 rounds to appear (AC38).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachInterviewDebrief, CoachPatternDismissal
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.coach_session import InterviewSession
from app.models.question_bank import QuestionBankItem
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    ReportInputSnapshot,
    build_conversational_report,
)
from app.services.coach_readiness import brief as brief_service
from app.services.coach_readiness.signals import load_signals, question_keys

NOW = datetime.utcnow()


def _qb_item() -> QuestionBankItem:
    return QuestionBankItem(
        id="qb-1", type="interview_question", title="Delivery question",
        question="Tell me about stakeholder management.",
        skills=["stakeholder management"], tags=["influence"],
    )


def test_question_tagging_uses_source_item_and_contained_keys() -> None:
    coverage_keys = (("Stakeholder management", "stakeholder management"),)

    from_source = question_keys(
        "Anything at all",
        {"kind": "question_bank_item", "id": "qb-1"},
        _qb_item(),
        coverage_keys,
    )
    contained = question_keys(
        "How do you handle stakeholder management under pressure?",
        None,
        None,
        coverage_keys,
    )
    empty = question_keys("Tell me about yourself", None, None, coverage_keys)

    assert from_source == frozenset({"stakeholder management", "influence"})
    assert contained == frozenset({"stakeholder management"})
    assert empty == frozenset()


async def _seed_base(db: AsyncSession) -> None:
    if await db.get(Application, "sig-app") is not None:
        return
    db.add(Application(id="sig-app", job_id="sig-job", status="interview", priority="normal"))
    db.add(JobPosting(
        id="sig-job", title="Delivery Lead", company="Northwind",
        url="https://example.test/sig", source="synthetic",
        description="Lead delivery.",
        skills=["Stakeholder management"],
    ))
    db.add(JobScore(
        id="sig-score", job_id="sig-job", overall_score=0.9,
        keyword_matches=[], keyword_misses=[],
        scoring_method="local",
    ))
    await db.commit()


async def _add_round(
    db: AsyncSession, index: int, *, rating: int | None = 2
) -> str:
    round_id = f"sig-round-{index}"
    db.add(InterviewRound(
        id=round_id, application_id="sig-app", round_number=index + 1,
        type="behavioural", scheduled_at=NOW - timedelta(days=index + 1),
        status="completed",
    ))
    db.add(CoachInterviewDebrief(
        interview_round_id=round_id,
        version=1,
        status="saved",
        overall=3,
        questions_json=[{
            "id": f"q-{index}", "text": "How do you handle stakeholder management?",
            "source_ref": None, "asked": True, "rating": rating,
            "story_id": None, "note": None,
        }],
        proposals_json=[],
        created_at=NOW, updated_at=NOW,
    ))
    await db.commit()
    return round_id


@pytest.mark.asyncio
async def test_signal_needs_two_rounds(db_session: AsyncSession) -> None:
    await _seed_base(db_session)
    await _add_round(db_session, 0)
    assert await load_signals(db_session) == ()

    await _add_round(db_session, 1)
    signals = await load_signals(db_session)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.display == "Stakeholder management"
    assert signal.asked_rounds == 2
    assert signal.low_rating_debriefs == 2


@pytest.mark.asyncio
async def test_signals_never_change_pattern_kind_or_trend(
    db_session: AsyncSession,
) -> None:
    from app.services.coach_conversational_progress import ProgressSnapshot
    from app.services.coach_readiness import patterns as pattern_module
    from app.services.coach_readiness.contracts import PatternPolicy

    snapshots = tuple(
        ProgressSnapshot(
            session_id=f"sig-session-{index}",
            compatibility_key=f"key-{index}",
            activity_version=1,
            completed_at=datetime(2026, 11, index + 1),
            session_level="needs_work",
            dimensions={"specificity": "needs_work"},
            role_family="Delivery Lead",
            role_level="senior",
            interview_type="behavioural",
            evaluation_contract_version="coach_conversational_report_v1",
            difficulty="realistic",
        )
        for index in range(2)
    )
    dismissed = frozenset(
        (
            await db_session.execute(select(CoachPatternDismissal.fingerprint))
        ).scalars().all()
    )
    before = pattern_module.derive_patterns(
        snapshots, dismissed, PatternPolicy(), NOW
    )

    await _seed_base(db_session)
    await _add_round(db_session, 0)
    await _add_round(db_session, 1)
    derived = await load_signals(db_session)
    assert derived

    after = pattern_module.derive_patterns(
        snapshots, dismissed, PatternPolicy(), NOW
    )
    assert after == before


@pytest.mark.asyncio
async def test_brief_watchouts_include_signals_after_practice_patterns(
    db_session: AsyncSession,
) -> None:
    # No practice sessions: the watch-out slots fill from real signals.
    await _seed_base(db_session)
    await _add_round(db_session, 0)
    await _add_round(db_session, 1)
    data = await brief_service.build_brief(db_session, "sig-round-0", NOW)
    assert data is not None
    assert [
        (item["dimension"], item["source"]) for item in data["watch_outs"]
    ] == [("Stakeholder management", "real_interview")]

    # A practice pattern takes the first slot; the signal fills the second.
    for index in (10, 11):
        report = build_conversational_report(
            ReportInputSnapshot(
                session_id=f"sig-practice-{index}",
                activity_version=1,
                retention_version=0,
                compatibility_key=f"key-{index}",
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
                            f"answer-{index}-{root}", {"specificity": "needs_work"}
                        ),
                        (),
                    )
                    for root in (1, 2)
                ),
            )
        )
        db_session.add(InterviewSession(
            id=f"sig-practice-{index}",
            application_id="sig-app",
            company_name="Northwind",
            role_title="Delivery Lead",
            config={},
            status="completed",
            conversation_state="completed",
            experience_version="conversational_v1",
            completed_at=datetime(2026, 11, index),
            activity_version=1,
            report_state="completed",
            report_json=report.persisted_json(),
            compatibility_key=f"key-{index}",
            session_plan_json={
                "role": {"role_family": "Delivery Lead", "role_level": "senior"},
                "interview": {"type": "behavioural", "difficulty": "realistic"},
            },
        ))
    await db_session.commit()

    data = await brief_service.build_brief(db_session, "sig-round-0", NOW)
    assert data is not None
    assert [
        (item["dimension"], item["source"]) for item in data["watch_outs"]
    ] == [
        ("specificity", "practice"),
        ("Stakeholder management", "real_interview"),
    ]
