"""Privacy contracts for Job Scoring SHADOW metadata."""

from datetime import datetime, timedelta

from app.runtime.evaluation.models import ShadowComparisonRecord
from app.runtime_bindings.migration.facade import record_job_score_shadow_comparison
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _request() -> JobScoreInput:
    return JobScoreInput(
        job_ref="job:synthetic-001",
        profile_ref="profile:current",
        event_ref="event:synthetic-001",
    )


def _result(score: float) -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=score,
        experience_match=score,
        rate_match=score,
        location_match=score,
        overall_score=score,
        reasoning="synthetic_reason",
        keyword_matches=("AWS",),
        keyword_misses=(),
        fit_reasoning="synthetic_fit_reason",
        strengths=("AWS",),
        score_gaps=(),
        scoring_method="local",
    )


async def test_shadow_persists_only_bounded_metadata_for_at_most_thirty_days(
    workflow_runtime,
) -> None:
    created_at = datetime(2030, 1, 1)
    _, factory = workflow_runtime
    async with factory.transaction() as uow:
        record = await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(0.8),
            runtime_result=_result(0.75),
            latency_ms=12,
            input_tokens=20,
            output_tokens=4,
            cost_microusd=1,
            created_at=created_at,
        )
        await uow.commit()

    async with factory.session_factory() as session:
        persisted = await session.get(ShadowComparisonRecord, record.id)
        assert persisted is not None
        assert persisted.expires_at == created_at + timedelta(days=30)
        assert persisted.metrics_json == {
            "score_delta": 0.05,
            "shortlist_agreement": True,
            "task_version": 1,
            "latency_ms": 12,
            "input_tokens": 20,
            "output_tokens": 4,
            "cost_microusd": 1,
            "reason_code": "score_delta",
        }
        assert "synthetic_reason" not in str(persisted.metrics_json)
        assert persisted.legacy_result_hash != persisted.runtime_result_hash
