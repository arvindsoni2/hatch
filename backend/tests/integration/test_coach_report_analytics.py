"""Persisted analytical source and lifecycle report contracts."""

import json
from datetime import datetime
import pytest
from app.models.coach_session import (
    InterviewSession,
    SessionRecording,
    SessionQuestion,
    InterviewTranscriptVersion,
    InterviewAttemptEvaluation,
    InterviewSessionEvent,
    CoachSessionEvidenceRecord,
)
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from test_coach_report_privacy_flow import synthetic_session, read_report_http


async def seed_populated_report(factory):
    """Persist lifecycle rows, current accepted sources and adversarial noncontributors."""
    from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS

    async with factory() as db:
        row = synthetic_session(id="populated-report", activity_version=7)
        db.add(row)
        await db.flush()
        questions = [
            SessionQuestion(
                id=f"root-{n}",
                session_id=row.id,
                question_num=n,
                text=f"Synthetic question {n}",
                category="Behavioural",
                order_in_session=n,
                question_state="answered" if n < 3 else "skipped",
            )
            for n in range(1, 4)
        ]
        db.add_all(questions)
        await db.flush()
        followup = SessionQuestion(
            id="followup",
            session_id=row.id,
            question_num=4,
            text="Synthetic follow-up",
            category="Behavioural",
            order_in_session=4,
            question_kind="adaptive_follow_up",
            root_question_id="root-1",
            parent_question_id="root-1",
            follow_up_depth=1,
            question_state="answered",
            follow_up_target_dimension="structure",
            follow_up_aggregation_role="gap_repair",
        )
        db.add(followup)
        await db.flush()
        for question in [*questions[:2], followup]:
            attempt = SessionRecording(
                id=f"accepted-{question.id}",
                session_id=row.id,
                question_id=question.id,
                recording_type="text",
                attempt_kind="primary"
                if question.question_kind == "planned"
                else "follow_up",
                attempt_number=1,
                attempt_state="completed",
                evaluation_state="completed",
                transcript="Synthetic answer",
                accepted_at=datetime.utcnow(),
            )
            db.add(attempt)
            await db.flush()
            transcript = InterviewTranscriptVersion(
                id=f"transcript-{question.id}",
                recording_id=attempt.id,
                version_number=1,
                transcript=attempt.transcript,
                source="candidate_text",
                created_by="candidate",
                processing_generation=0,
            )
            db.add(transcript)
            await db.flush()
            evaluation = InterviewAttemptEvaluation(
                id=f"evaluation-{question.id}",
                recording_id=attempt.id,
                transcript_version_id=transcript.id,
                version_number=1,
                state="completed",
                answer_level="developing",
                rubric_json={
                    "dimensions": dict(
                        zip(
                            CONTENT_DIMENSIONS,
                            (
                                {"level": level}
                                for level in (
                                    "strong",
                                    "developing",
                                    "interview_ready",
                                    "interview_ready",
                                    "not_assessed",
                                    "not_assessed",
                                    "not_assessed",
                                )
                            ),
                        )
                    )
                },
                evidence_findings_json={
                    "level": "developing",
                    "claims": [
                        {
                            "claim_id": "synthetic-claim",
                            "claim_text": "Synthetic answer",
                            "transcript_start": 0,
                            "transcript_end": 16,
                            "status": "partially_supported",
                            "evidence_ids": ["approved-evidence"],
                            "explanation": "Review the selected evidence.",
                            "candidate_action": "Confirm the detail before reuse.",
                        }
                    ],
                },
                evaluation_contract_version="coach_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
            )
            db.add(evaluation)
            await db.flush()
            attempt.current_transcript_version_id = transcript.id
            attempt.current_evaluation_version_id = evaluation.id
            question.accepted_recording_id = attempt.id
        db.add_all(
            [
                SessionRecording(
                    id="unaccepted-retry",
                    session_id=row.id,
                    question_id="root-1",
                    recording_type="text",
                    attempt_kind="retry",
                    attempt_number=2,
                    attempt_state="completed",
                ),
                SessionRecording(
                    id="unavailable-retry",
                    session_id=row.id,
                    question_id="root-1",
                    recording_type="text",
                    attempt_kind="retry",
                    attempt_number=3,
                    attempt_state="unavailable",
                ),
                CoachSessionEvidenceRecord(
                    session_id=row.id,
                    evidence_id="approved-evidence",
                    source_type="master_cv",
                    source_record_id="synthetic-source",
                    source_record_version="1",
                    source_path="synthetic.source",
                    snapshot_text="Synthetic approved evidence",
                    approval_state="approved",
                    content_hash="a" * 64,
                    snapshot_hash="b" * 64,
                ),
            ]
        )
        for n, event_type in enumerate(
            ("hint_requested", "hint_presented", "hint_presented"), 1
        ):
            db.add(
                InterviewSessionEvent(
                    session_id=row.id,
                    sequence_number=n,
                    event_type=event_type,
                    state_version=0,
                    actor_type="candidate",
                )
            )
        row.event_version = 3
        await db.commit()


async def test_populated_repository_report_has_exact_counts_and_current_source_links(
    coach_database,
):
    from app.services.coach_conversational_report import build_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        repository = ConversationalSessionRepository(db)
        snapshot = await repository.load_report_input_snapshot("populated-report", 7)
        assert dict(snapshot.counts) == {
            "planned_questions_total": 3,
            "planned_questions_answered": 2,
            "planned_questions_skipped": 1,
            "follow_ups_asked": 1,
            "follow_ups_answered": 1,
            "accepted_attempts": 3,
            "retry_attempts": 2,
            "unavailable_attempts": 1,
            "hints_used": 2,
        }
        report = build_conversational_report(snapshot).persisted_json()
        assert len(report["strengths"]) == 3
        assert len(report["question_summaries"]) == 4
        assert {item["attempt_id"] for item in report["evidence_review_items"]} == {
            "accepted-root-1",
            "accepted-root-2",
            "accepted-followup",
        }
        assert (
            report["question_summaries"][0]["accepted_attempt_id"] == "accepted-root-1"
        )
        assert "unaccepted-retry" not in json.dumps(report)
        row = await db.get(InterviewSession, "populated-report")
        row.report_json = report
        row.report_state = "completed"
        await db.commit()
    response = await read_report_http(coach_database, "populated-report")
    assert response.status_code == 200, response.text
    assert len(response.json()["practice_suggestions"]) == 2


@pytest.mark.parametrize(
    "invalidate",
    ["deleted", "stale_transcript", "foreign_evaluation", "source_deleted"],
)
async def test_report_excludes_deleted_and_noncurrent_accepted_sources(
    coach_database, invalidate
):
    from app.services.coach_conversational_report import build_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        attempt = await db.get(SessionRecording, "accepted-root-1")
        if invalidate == "deleted":
            attempt.attempt_state = "deleted"
        elif invalidate == "stale_transcript":
            attempt.current_transcript_version_id = None
        elif invalidate == "foreign_evaluation":
            attempt.current_evaluation_version_id = "evaluation-root-2"
        else:
            question = await db.get(SessionQuestion, "root-1")
            question.source_deleted = True
        await db.commit()
        repository = ConversationalSessionRepository(db)
        snapshot = await repository.load_report_input_snapshot("populated-report", 7)
        report = build_conversational_report(snapshot).persisted_json()
        assert not any(
            item["attempt_id"] == "accepted-root-1"
            for item in report["evidence_review_items"]
        )
        assert not any(
            item["accepted_attempt_id"] == "accepted-root-1"
            for item in report["question_summaries"]
        )
        assert (
            await repository.load_report_input_snapshot("populated-report", 6) is None
        )


async def test_orphan_followup_cannot_contribute_after_root_source_disappears(
    coach_database,
):
    from app.services.coach_conversational_report import build_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        root = await db.get(SessionRecording, "accepted-root-1")
        root.attempt_state = "deleted"
        await db.commit()
        snapshot = await ConversationalSessionRepository(db).load_report_input_snapshot(
            "populated-report", 7
        )
        report = build_conversational_report(snapshot).persisted_json()
        assert not any(
            item["attempt_id"] == "accepted-followup"
            for item in report["evidence_review_items"]
        )


async def test_report_preserves_not_verifiable_evidence_status(coach_database):
    from app.services.coach_conversational_report import build_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        evaluation = await db.get(InterviewAttemptEvaluation, "evaluation-root-1")
        findings = dict(evaluation.evidence_findings_json)
        findings["claims"] = [{**findings["claims"][0], "status": "not_verifiable"}]
        evaluation.evidence_findings_json = findings
        await db.commit()
        snapshot = await ConversationalSessionRepository(db).load_report_input_snapshot(
            "populated-report", 7
        )
        report = build_conversational_report(snapshot).persisted_json()
        assert [
            item["status"]
            for item in report["evidence_review_items"]
            if item["attempt_id"] == "accepted-root-1"
        ] == ["not_verifiable"]


async def test_read_rejects_incomplete_dimension_analysis(coach_database):
    from app.services.coach_conversational_report import build_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        snapshot = await ConversationalSessionRepository(db).load_report_input_snapshot(
            "populated-report", 7
        )
        report = build_conversational_report(snapshot).persisted_json()
        report["dimensions"].pop("structure")
        row = await db.get(InterviewSession, "populated-report")
        row.report_state = "completed"
        row.report_json = report
        await db.commit()
    response = await read_report_http(coach_database, "populated-report")
    assert response.status_code == 409
