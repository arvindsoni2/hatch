from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.coach_coaching import (
    CoachAnswerReview,
    CoachCoachingService,
    build_coaching_skeleton,
    validate_coaching_enrichment,
)
from app.services.coach_text_spans import ContractValidationError


TRANSCRIPT = "I led the migration and reduced deployment time by three hours."
EVALUATION = {
    "answer_level": "interview_ready",
    "dimensions": {
        "relevance": {
            "level": "strong",
            "evidence": [
                {
                    "transcript_start": 0,
                    "transcript_end": len(TRANSCRIPT),
                    "excerpt": TRANSCRIPT,
                }
            ],
            "rationale": "The answer directly addresses the migration.",
            "improvement": "Add the principal constraint.",
        },
        "impact": {
            "level": "developing",
            "evidence": [
                {
                    "transcript_start": 0,
                    "transcript_end": len(TRANSCRIPT),
                    "excerpt": TRANSCRIPT,
                }
            ],
            "rationale": "The result is concrete but its significance is unclear.",
            "improvement": "Explain why three hours mattered.",
        },
    },
    "evidence_consistency": {
        "level": "partially_supported",
        "claims": [
            {
                "status": "partially_supported",
                "explanation": "The migration is supported; the timing needs review.",
                "candidate_action": "Review the timing detail.",
            }
        ],
    },
}


class FailingModel:
    async def complete_json(self, *_args, **_kwargs):
        raise RuntimeError("offline")


def test_skeleton_is_deterministic_and_uses_validated_evaluation_only() -> None:
    review = build_coaching_skeleton(EVALUATION)

    assert review.answer_level == "interview_ready"
    assert review.positive_observation == "The answer directly addresses the migration."
    assert review.priority_improvement == "Explain why three hours mattered."
    assert review.transcript_evidence == (TRANSCRIPT,)
    assert review.example_revision == "[add verified metric]"
    assert review.evidence_review_items == (
        "The migration is supported; the timing needs review.",
    )


@pytest.mark.asyncio
async def test_unavailable_model_returns_deterministic_skeleton() -> None:
    skeleton = build_coaching_skeleton(EVALUATION)

    review = await CoachCoachingService(FailingModel()).enrich(
        skeleton,
        transcript=TRANSCRIPT,
        evidence_texts=(),
        deadline_at=datetime.utcnow() + timedelta(seconds=5),
    )

    assert review == skeleton


@pytest.mark.parametrize(
    "invented",
    ["saved 37%", "led Project Orion", "managed 40 people"],
)
def test_enrichment_cannot_invent_candidate_facts(invented: str) -> None:
    with pytest.raises(
        ContractValidationError, match="coach_evaluation_prohibited_inference"
    ):
        validate_coaching_enrichment(
            {
                "positive_observation": "The answer directly addresses the migration.",
                "priority_improvement": "Explain why three hours mattered.",
                "suggested_structure": "Lead with the action, then the result.",
                "practice_instruction": "Practise this answer once.",
                "example_revision": invented,
            },
            transcript=TRANSCRIPT,
            evidence_texts=(),
        )


def test_enrichment_allows_candidate_words_and_missing_metric_token() -> None:
    review = validate_coaching_enrichment(
        {
            "positive_observation": "I led the migration.",
            "priority_improvement": "Explain why three hours mattered.",
            "suggested_structure": "I led the migration, then [add verified metric].",
            "practice_instruction": "Practise the migration answer.",
            "example_revision": "I led the migration and [add verified metric].",
        },
        transcript=TRANSCRIPT,
        evidence_texts=(),
    )

    assert isinstance(review, CoachAnswerReview)
    assert "[add verified metric]" in review.example_revision


def test_enrichment_cannot_change_levels_or_hide_evidence_conflict() -> None:
    with pytest.raises(ContractValidationError):
        validate_coaching_enrichment(
            {
                "answer_level": "strong",
                "positive_observation": "I led the migration.",
                "priority_improvement": "Explain why three hours mattered.",
                "suggested_structure": "Action then result.",
                "practice_instruction": "Practise once.",
                "example_revision": "I led the migration.",
            },
            transcript=TRANSCRIPT,
            evidence_texts=(),
        )
