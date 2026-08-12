from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.coach_followup_policy import FollowUpContext, FollowUpPolicy


TRANSCRIPT = "I led the migration and the stakeholders were satisfied."
EXCERPT = "the stakeholders were satisfied"
START = TRANSCRIPT.index(EXCERPT)


def proposal(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "should_ask": True,
        "reason": "measurable_result",
        "question": "What measurable outcome resulted from your intervention?",
        "transcript_evidence": {
            "start": START,
            "end": START + len(EXCERPT),
            "excerpt": EXCERPT,
        },
        "target_dimension": "impact",
        "aggregation_role": "gap_repair",
        "duplicate_key": "root-question:impact:result",
    }
    value.update(overrides)
    return value


def context(**overrides: object) -> FollowUpContext:
    value = FollowUpContext(
        transcript=TRANSCRIPT,
        accepted_attempt_id="attempt-1",
        current_accepted_attempt_id="attempt-1",
        target_dimension_levels={"impact": "developing"},
        existing_duplicate_keys=(),
        persisted_follow_up_count=0,
        root_skipped=False,
        session_ended=False,
    )
    return replace(value, **overrides)


def test_valid_gap_repair_proposal_is_admitted_with_canonical_mapping() -> None:
    decision = FollowUpPolicy().validate(proposal(), context())

    assert decision.admitted is True
    assert decision.reason == "measurable_result"
    assert decision.target_dimension == "impact"
    assert decision.aggregation_role == "gap_repair"
    assert decision.duplicate_key == "root-question:impact:result"
    assert decision.transcript_start == START
    assert decision.transcript_end == START + len(EXCERPT)


@pytest.mark.parametrize(
    ("candidate", "candidate_context"),
    [
        (
            proposal(target_dimension="specificity"),
            context(),
        ),
        (
            proposal(),
            context(target_dimension_levels={"impact": "interview_ready"}),
        ),
        (
            proposal(
                transcript_evidence={
                    "start": START,
                    "end": START + len(EXCERPT),
                    "excerpt": "invented result",
                }
            ),
            context(),
        ),
        (
            proposal(question="You scored 4/10, so explain your confidence."),
            context(),
        ),
        (
            proposal(),
            context(existing_duplicate_keys=("root-question:impact:result",)),
        ),
        (
            proposal(),
            context(persisted_follow_up_count=2),
        ),
        (
            proposal(),
            context(current_accepted_attempt_id="attempt-replaced"),
        ),
        (
            proposal(),
            context(root_skipped=True),
        ),
        (
            proposal(),
            context(session_ended=True),
        ),
    ],
)
def test_invalid_follow_up_proposals_are_rejected(
    candidate: dict[str, object], candidate_context: FollowUpContext
) -> None:
    assert FollowUpPolicy().validate(candidate, candidate_context).admitted is False


def test_should_ask_false_is_a_valid_no_follow_up_decision() -> None:
    decision = FollowUpPolicy().validate(
        {
            "should_ask": False,
            "reason": None,
            "question": None,
            "transcript_evidence": None,
            "target_dimension": None,
            "aggregation_role": None,
            "duplicate_key": None,
        },
        context(),
    )

    assert decision.admitted is False
    assert decision.error_code is None
