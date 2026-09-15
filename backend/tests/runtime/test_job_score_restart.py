"""Recovery contracts proving R5 consumes the shared fenced workflow kernel."""

from datetime import datetime

import asyncio
import pytest
from sqlalchemy import select

from app.runtime.workflow.models import TaskAttemptRecord, WorkflowStepRecord
from workflow_test_support import synthetic_spec
from job_score_test_support import job, profile, install_profile
from app.models.job_score import JobScore
from app.agents.scorer_agent import ScorerAgent
from app.runtime import RuntimeMode
from app.runtime_bindings.migration.scoring import RuntimeScoringOperation

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


async def test_runtime_reclaims_expired_work_and_fences_stale_claim(
    workflow_runtime,
) -> None:
    kernel, _ = workflow_runtime
    runtime = DurableJobScoreRuntime(kernel, worker_id="job-score-worker")
    run, first_claim = await runtime.start(_request())

    recovered = await kernel.reconcile(datetime(2030, 1, 1, 0, 1, 0))
    second_claim = await kernel.claim_next(
        "replacement-worker", datetime(2030, 1, 1, 0, 1, 1)
    )

    assert recovered == 1
    assert second_claim is not None
    assert second_claim.task_attempt_id == first_claim.task_attempt_id
    completed_at = datetime(2030, 1, 1, 0, 1, 2)
    assert not await runtime.complete(first_claim, _result(), now=completed_at)
    assert await runtime.complete(second_claim, _result(), now=completed_at)
    assert run.workflow_definition_id == "job.score"


async def test_start_claims_only_its_run_with_older_unrelated_work(workflow_runtime):
    kernel, factory = workflow_runtime
    unrelated = await kernel.start_run(
        synthetic_spec(),
        input_ref={"input_ref": "other"},
        domain_ref={"domain_id": "other"},
        mode="new",
    )
    runtime = DurableJobScoreRuntime(kernel, worker_id="scorer")
    run, claim = await runtime.start(_request())
    assert (await kernel.get_claim_correlation(claim))["workflow_run_id"] == run.id
    async with factory.session_factory() as session:
        attempt = await session.scalar(
            select(TaskAttemptRecord)
            .join(WorkflowStepRecord)
            .where(WorkflowStepRecord.workflow_run_id == unrelated.id)
        )
        assert attempt.status == "pending"
        assert attempt.current_claim_id is None


async def test_concurrent_starts_keep_claims_and_results_isolated(workflow_runtime):
    kernel, factory = workflow_runtime
    runtimes = [
        DurableJobScoreRuntime(kernel, worker_id=f"scorer-{i}") for i in range(3)
    ]
    started = await asyncio.gather(
        *(
            runtime.start(
                _request().model_copy(update={"job_ref": f"job:synthetic-{i}"})
            )
            for i, runtime in enumerate(runtimes)
        )
    )
    assert len({claim.task_attempt_id for _, claim in started}) == 3
    for runtime, (run, claim) in zip(runtimes, started):
        assert (await kernel.get_claim_correlation(claim))["workflow_run_id"] == run.id
        assert await runtime.complete(claim, _result())
        assert not await runtime.complete(claim, _result())


async def test_projection_failure_rolls_back_finalization_and_replay_is_fenced(
    workflow_runtime,
):
    kernel, factory = workflow_runtime
    runtime = DurableJobScoreRuntime(kernel, worker_id="scorer")
    _, claim = await runtime.start(_request())

    async def crash(uow):
        raise RuntimeError("synthetic_projection_crash")

    with pytest.raises(RuntimeError, match="synthetic_projection_crash"):
        await runtime.complete(claim, _result(), projection=crash)
    assert (await kernel.get_attempt(claim.task_attempt_id)).status == "running"
    assert await runtime.complete(claim, _result())
    # A released owner must never invoke a projection again.
    assert not await runtime.complete(claim, _result(), projection=crash)


async def test_restart_reuses_bound_context_and_persisted_mode_for_one_projection(
    workflow_runtime, monkeypatch
):
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile())
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
    request = _request().model_copy(update={"job_ref": f"job:{posting.id}"})
    first = DurableJobScoreRuntime(kernel, worker_id="before-crash", factory=factory)
    run, stale = await first.start(request, mode=RuntimeMode.NEW)
    await RuntimeScoringOperation(factory, kernel, request).prepare(stale)
    context_id = (await kernel.get_attempt(stale.task_attempt_id)).context_package_id
    assert await kernel.reconcile(datetime(2030, 1, 1, 0, 1)) == 1
    monkeypatch.setattr(kernel.clock, "now", lambda: datetime(2030, 1, 1, 0, 1, 2))
    replacement = DurableJobScoreRuntime(
        kernel, worker_id="after-crash", factory=factory
    )
    scorer = ScorerAgent(runtime_factory=factory)

    async def project(uow, output, usage):
        await scorer._write_visible_score(posting.id, output, uow.session, commit=False)

    result = await replacement.resume(run.id, projection=project)
    assert result.output.overall_score == 0.89
    assert (
        await kernel.get_attempt(stale.task_attempt_id)
    ).context_package_id == context_id
    assert not await first.complete(stale, _result())
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        assert len(scores) == 1
        assert scores[0].overall_score == 0.89
    with pytest.raises(RuntimeError, match="claim_unavailable"):
        await replacement.resume(run.id, projection=project)


async def test_runtime_execution_span_links_real_durable_ids(
    workflow_runtime, monkeypatch
):
    from app.observability.runtime import TelemetryRuntime
    from app.runtime.evaluation.models import ExecutionRecord
    from app.runtime.observability import RuntimeCorrelation

    started = []

    class Span:
        def set_attribute(self, *args):
            pass

        def set_status(self, *args):
            pass

    class Manager:
        def __enter__(self):
            return Span()

        def __exit__(self, *args):
            return False

    class Tracer:
        def start_as_current_span(self, name, **kwargs):
            started.append((name, kwargs))
            return Manager()

    telemetry = TelemetryRuntime(status="active", tracer=Tracer())
    monkeypatch.setattr(
        "app.runtime.observability.tracing.get_telemetry", lambda: telemetry
    )
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile())
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
    runtime = DurableJobScoreRuntime(kernel, worker_id="traced", factory=factory)
    result = await runtime.score_job(
        _request().model_copy(update={"job_ref": f"job:{posting.id}"}),
        mode=RuntimeMode.SHADOW,
    )
    async with factory.session_factory() as session:
        execution = await session.get(ExecutionRecord, result.execution_id)
        attempt = await session.get(TaskAttemptRecord, execution.task_attempt_id)
        expected = RuntimeCorrelation(
            workflow_run_id=result.run_id,
            workflow_step_id=attempt.workflow_step_id,
            task_attempt_id=attempt.id,
            execution_id=execution.id,
            task_id="job.score",
            task_version=1,
        ).trace_attributes()
    matching = [
        data
        for _, data in started
        if all(data["attributes"].get(k) == v for k, v in expected.items())
    ]
    assert matching
    assert all(data["record_exception"] is False for data in matching)
    assert "SYNTHETIC_PRIVATE_CANARY" not in repr(started)


async def test_concurrent_real_runtime_projections_collide_without_duplicate_scores(
    workflow_runtime, monkeypatch
):
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile())
    async with factory.session_factory() as session:
        posting = job()
        other = job(
            title="Junior Clerk",
            description="Synthetic unrelated packing duties",
            location="Santiago",
        )
        session.add_all([posting, other])
        await session.commit()
    scorer = ScorerAgent(runtime_factory=factory)

    async def execute(index, job_id):
        runtime = DurableJobScoreRuntime(
            kernel, worker_id=f"collision-{index}", factory=factory
        )

        async def project(uow, output, usage):
            await scorer._write_visible_score(job_id, output, uow.session, commit=False)

        return await runtime.score_job(
            _request().model_copy(
                update={
                    "job_ref": f"job:{job_id}",
                    "event_ref": f"event:collision-{index}",
                }
            ),
            mode=RuntimeMode.NEW,
            projection=project,
        )

    results = await asyncio.gather(
        execute(0, posting.id), execute(1, posting.id), execute(2, other.id)
    )
    assert len({result.run_id for result in results}) == 3
    async with factory.session_factory() as session:
        scores = {
            row.job_id: row.overall_score
            for row in await session.scalars(select(JobScore))
        }
        assert scores == {posting.id: 0.89, other.id: results[2].output.overall_score}
        assert scores[other.id] < scores[posting.id]
