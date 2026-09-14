"""Recovery contracts proving R5 consumes the shared fenced workflow kernel."""

from datetime import datetime

from app.runtime_bindings.migration.job_score import DurableJobScoreRuntime
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _request() -> JobScoreInput:
    return JobScoreInput(
        job_ref="job:synthetic-001",
        profile_ref="profile:current",
        event_ref="event:synthetic-001",
    )


def _result() -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=0.8,
        experience_match=0.8,
        rate_match=0.8,
        location_match=0.8,
        overall_score=0.8,
        reasoning="synthetic_reason",
        keyword_matches=("AWS",),
        keyword_misses=(),
        fit_reasoning="synthetic_fit_reason",
        strengths=("AWS",),
        score_gaps=(),
        scoring_method="local",
    )


async def test_runtime_reclaims_expired_work_and_fences_stale_claim(workflow_runtime) -> None:
    kernel, _ = workflow_runtime
    runtime = DurableJobScoreRuntime(kernel, worker_id="job-score-worker")
    run, first_claim = await runtime.start(_request())

    recovered = await kernel.reconcile(datetime(2030, 1, 1, 0, 1, 0))
    second_claim = await kernel.claim_next("replacement-worker", datetime(2030, 1, 1, 0, 1, 1))

    assert recovered == 1
    assert second_claim is not None
    assert second_claim.task_attempt_id == first_claim.task_attempt_id
    completed_at = datetime(2030, 1, 1, 0, 1, 2)
    assert not await runtime.complete(first_claim, _result(), now=completed_at)
    assert await runtime.complete(second_claim, _result(), now=completed_at)
    assert run.workflow_definition_id == "job.score"
