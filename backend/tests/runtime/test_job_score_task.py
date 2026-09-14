"""Task-contract tests for the R5 Job Scoring runtime binding."""

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionStrategy
from app.runtime_bindings.tasks.job_score import (
    JOB_SCORE_V1,
    JobScoreInput,
    JobScoreOutput,
)


def test_job_score_v1_is_an_immutable_reference_only_fallback_contract() -> None:
    assert JOB_SCORE_V1.task_id == "job.score"
    assert JOB_SCORE_V1.version == 1
    assert JOB_SCORE_V1.input_model is JobScoreInput
    assert JOB_SCORE_V1.output_model is JobScoreOutput
    assert JOB_SCORE_V1.execution_strategy is ExecutionStrategy.FALLBACK_ON_FAILURE
    assert {item.capability for item in JOB_SCORE_V1.context_requirements} == {
        "candidate.profile_summary",
        "candidate.resume_text",
        "job.description",
        "job.requirements",
    }
    assert JOB_SCORE_V1.workflow_policy.max_attempts == 2


def test_job_score_contract_has_reference_input_and_legacy_durable_output_shape() -> None:
    request = JobScoreInput(
        job_ref="job:synthetic-001",
        profile_ref="profile:current",
        event_ref="event:synthetic-001",
    )
    result = JobScoreOutput(
        skill_match=0.8,
        experience_match=0.7,
        rate_match=0.6,
        location_match=0.9,
        overall_score=0.735,
        reasoning="synthetic_reason",
        keyword_matches=("AWS",),
        keyword_misses=("Kubernetes",),
        fit_reasoning="synthetic_fit_reason",
        strengths=("AWS",),
        score_gaps=("Kubernetes",),
        scoring_method="local",
    )

    assert request.model_dump() == {
        "job_ref": "job:synthetic-001",
        "profile_ref": "profile:current",
        "event_ref": "event:synthetic-001",
    }
    assert result.overall_score == 0.735
    assert result.scoring_method == "local"
    assert RuntimeMode.LEGACY.value == "legacy"
