"""R5's product-level retention check uses the shared 30-day shadow store."""

from datetime import datetime

from sqlalchemy import select

from app.runtime.evaluation.models import ShadowComparisonRecord
from app.runtime_bindings.migration.facade import record_job_score_shadow_comparison
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _request() -> JobScoreInput:
    return JobScoreInput(
        job_ref="job:synthetic-002",
        profile_ref="profile:synthetic",
        event_ref="event:synthetic-002",
    )


def _result() -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=0.8,
        experience_match=0.8,
        rate_match=0.8,
        location_match=0.8,
        overall_score=0.8,
        reasoning="synthetic_reason",
        keyword_matches=(),
        keyword_misses=(),
        fit_reasoning=None,
        strengths=(),
        score_gaps=(),
        scoring_method="local",
    )


async def test_shadow_retention_purge_removes_expired_comparisons(workflow_runtime) -> None:
    _, factory = workflow_runtime
    async with factory.transaction() as uow:
        await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(),
            runtime_result=_result(),
            created_at=datetime(2030, 1, 1),
        )
        await uow.commit()

    async with factory.transaction() as uow:
        assert await uow.shadow.purge_expired(now=datetime(2030, 1, 31)) == 1
        await uow.commit()

    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ShadowComparisonRecord))).all()) == []
