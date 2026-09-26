"""Durable pre-execution ownership for concurrent/restarted scoring consumers."""

import asyncio
import json
import multiprocessing
from queue import Empty
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.agents import scorer_agent as scorer_module
from app.agents.scorer_agent import ScorerAgent
from app.agents.tools.event_bus import EventBus
from app.config import settings
from app.database import get_db
from app.database import create_sqlite_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.main import app
from app.models.agent_event import AgentEvent
from app.models.cost_tracking import CostTracking
from app.models.job_score import JobScore
from app.runtime import RuntimeMode
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.evaluation.models import ExecutionRecord
from app.runtime.workflow import WorkflowKernel
from app.runtime.workflow.models import (
    ExecutionClaimRecord,
    WorkflowRunRecord,
    WorkflowStepRecord,
    TaskAttemptRecord,
)
from app.runtime_bindings.migration.job_score import DurableJobScoreRuntime
from app.runtime_bindings.tasks.job_score import JOB_SCORE_V1, JobScoreInput
from job_score_test_support import install_profile, install_provider, job, profile


async def test_concurrent_consumers_have_one_run_invocation_and_projection(
    workflow_runtime, monkeypatch
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    charges = []

    async def charged():
        charges.append("primary")

    install_provider(monkeypatch, [0.8, 0.8], on_primary=charged)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await EventBus().emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        await ScorerAgent(runtime_factory=factory).update_state(session, "idle")
    barrier = asyncio.Barrier(2)
    reconcile = scorer_module.reconcile_job_score_source_event

    async def both_read_unbound(event_id, session):
        result = await reconcile(event_id, session)
        if result is None:
            await session.rollback()
            await asyncio.wait_for(barrier.wait(), timeout=5)
        return result

    monkeypatch.setattr(
        scorer_module, "reconcile_job_score_source_event", both_read_unbound
    )

    async def consume():
        async with factory.session_factory() as session:
            scorer = ScorerAgent(runtime_factory=factory)
            scorer._bus = EventBus()
            return await scorer.run(session)

    await asyncio.wait_for(asyncio.gather(consume(), consume()), timeout=15)
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
        assert len(list(await session.scalars(select(ExecutionRecord)))) == 1
        assert len(list(await session.scalars(select(CostTracking)))) == 2
        assert len(list(await session.scalars(select(JobScore)))) == 1
        events = list(await session.scalars(select(AgentEvent)))
        assert sum(event.event_type == "job_scored" for event in events) == 1
        assert (
            next(e for e in events if e.event_type == "job_discovered").status
            == "completed"
        )
    assert charges == ["primary"]


@pytest.mark.parametrize("crash", ["before_start", "after_start", "after_claim"])
async def test_fresh_worker_recovers_source_crash_without_new_run_or_early_call(
    workflow_runtime, client, monkeypatch, crash
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    charges = []

    async def charged():
        charges.append("primary")

    install_provider(monkeypatch, [0.8, 0.8], on_primary=charged)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)

    async def request_db():
        async with factory.session_factory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, request_db)
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        event_id = await EventBus().emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        scorer = ScorerAgent(runtime_factory=factory)
        scorer._bus = EventBus()
        with monkeypatch.context() as fault:
            start = WorkflowKernel.start_run
            claim = WorkflowKernel.claim_run

            async def die_start(self, *args, **kwargs):
                if crash == "after_start":
                    await start(self, *args, **kwargs)
                raise asyncio.CancelledError()

            async def die_claim(self, *args, **kwargs):
                await claim(self, *args, **kwargs)
                raise asyncio.CancelledError()

            if crash == "after_claim":
                fault.setattr(WorkflowKernel, "claim_run", die_claim)
            else:
                fault.setattr(WorkflowKernel, "start_run", die_start)
            with pytest.raises(asyncio.CancelledError):
                await scorer.run(session)
    assert charges == []
    if crash == "after_claim":
        # A live lease is never permission to execute in a replacement worker.
        response = await client.post(f"/api/events/{event_id}/retry")
        assert response.status_code == 409
        async with factory.session_factory() as session:
            await ScorerAgent(runtime_factory=factory).run(session)
        assert charges == []
        async with factory.session_factory() as session:
            old_claim = await session.scalar(select(ExecutionClaimRecord))
            old_claim.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            await session.commit()
    async with factory.session_factory() as session:
        await ScorerAgent(runtime_factory=factory).run(session)
    async with factory.session_factory() as session:
        runs = list(await session.scalars(select(WorkflowRunRecord)))
        assert len(runs) == 1
        assert runs[0].status == "completed"
        assert len(list(await session.scalars(select(ExecutionRecord)))) == 1
        assert len(list(await session.scalars(select(CostTracking)))) == 2
        assert len(list(await session.scalars(select(JobScore)))) == 1
        source = await session.get(AgentEvent, event_id)
        assert source.status == "completed"
    response = await client.post(f"/api/events/{event_id}/retry")
    assert response.json()["status"] == "completed"
    assert charges == ["primary"]
    if crash == "after_claim":
        assert not await WorkflowKernel(factory).finalize(
            old_claim, {"result_ref": "stale-projection"}
        )


@pytest.mark.parametrize(
    "changed", [{"job_ref": "job:other"}, {"profile_ref": "profile:other"}]
)
async def test_same_source_cannot_be_rebound_to_another_job_or_profile(
    workflow_runtime, changed
):
    kernel, factory = workflow_runtime
    request = JobScoreInput(
        job_ref="job:first", profile_ref="profile:current", event_ref="event:shared"
    )
    runtime = DurableJobScoreRuntime(kernel, worker_id="first", factory=factory)
    await runtime.start(request, mode=RuntimeMode.NEW)
    replacement = DurableJobScoreRuntime(kernel, worker_id="second", factory=factory)
    with pytest.raises(ValueError, match="identity_conflict"):
        await replacement.start(
            request.model_copy(update=changed), mode=RuntimeMode.NEW
        )
    async with factory.session_factory() as session:
        runs = list(await session.scalars(select(WorkflowRunRecord)))
        assert len(runs) == 1
        assert runs[0].domain_id == "job:first"
        assert "job:other" not in json.dumps(runs[0].input_ref_json)


async def test_public_retry_rejects_cross_job_source_rebinding(
    workflow_runtime, client, monkeypatch
):
    kernel, factory = workflow_runtime

    async def request_db():
        async with factory.session_factory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, request_db)
    async with factory.session_factory() as session:
        source = AgentEvent(
            event_type="job_discovered",
            source_agent="scout",
            status="failed",
            payload=json.dumps({"job_id": "other"}),
        )
        session.add(source)
        await session.commit()
        event_id = source.id
    request = JobScoreInput(
        job_ref="job:first",
        profile_ref="profile:current",
        event_ref=f"event:{event_id}",
    )
    await DurableJobScoreRuntime(kernel, worker_id="first", factory=factory).start(
        request, mode=RuntimeMode.NEW
    )
    response = await client.post(f"/api/events/{event_id}/retry")
    assert response.status_code == 409
    assert "first" not in response.text
    async with factory.session_factory() as session:
        assert (await session.get(AgentEvent, event_id)).status == "failed"
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
        assert not list(await session.scalars(select(ExecutionRecord)))


async def test_fresh_worker_reuses_pre_idempotency_run(workflow_runtime, monkeypatch):
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    install_provider(monkeypatch, [0.8])
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        event_id = await EventBus().emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
    run = await kernel.start_run(
        JOB_SCORE_V1,
        input_ref={
            "job_ref": f"job:{posting.id}",
            "profile_ref": "profile:current",
            "event_ref": f"event:{event_id}",
        },
        domain_ref={"domain_type": "job_posting", "domain_id": f"job:{posting.id}"},
        mode="new",
    )
    async with factory.session_factory() as session:
        await ScorerAgent(runtime_factory=factory).run(session)
    async with factory.session_factory() as session:
        assert list(await session.scalars(select(WorkflowRunRecord.id))) == [run.id]
        assert (await session.get(WorkflowRunRecord, run.id)).status == "completed"
        assert len(list(await session.scalars(select(CostTracking)))) == 2


def _consume_in_process(db_url, barrier, observations):
    """Spawned worker uses real DB ownership; only provider transport is synthetic."""
    patch = pytest.MonkeyPatch()
    install_profile(patch, profile("llm"))

    async def charged():
        observations.put("primary")

    install_provider(patch, [0.8], on_primary=charged)
    patch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    reconcile = scorer_module.reconcile_job_score_source_event

    async def synchronize(event_id, session):
        result = await reconcile(event_id, session)
        if result is None:
            await session.rollback()
            await asyncio.to_thread(barrier.wait, 10)
        return result

    patch.setattr(scorer_module, "reconcile_job_score_source_event", synchronize)

    async def consume():
        engine = create_sqlite_engine(db_url)
        factory = SQLiteRuntimeUnitOfWorkFactory(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        try:
            async with factory.session_factory() as session:
                await ScorerAgent(runtime_factory=factory).run(session)
        finally:
            await engine.dispose()

    try:
        asyncio.run(consume())
        observations.put("completed")
    finally:
        patch.undo()


async def test_separate_processes_share_the_durable_source_boundary(workflow_runtime):
    _, factory = workflow_runtime
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await EventBus().emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        await ScorerAgent(runtime_factory=factory).update_state(session, "idle")
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    observations = context.Queue()
    workers = [
        context.Process(
            target=_consume_in_process,
            args=(str(factory.session_factory.kw["bind"].url), barrier, observations),
        )
        for _ in range(2)
    ]
    try:
        for worker in workers:
            worker.start()
        await asyncio.gather(
            *(asyncio.to_thread(worker.join, 25) for worker in workers)
        )
        assert [worker.exitcode for worker in workers] == [0, 0]
        recorded = []
        while True:
            try:
                recorded.append(observations.get_nowait())
            except Empty:
                break
        assert recorded.count("primary") == 1
        assert recorded.count("completed") == 2
        async with factory.session_factory() as session:
            assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
            assert len(list(await session.scalars(select(ExecutionRecord)))) == 1
            assert len(list(await session.scalars(select(CostTracking)))) == 2
            assert len(list(await session.scalars(select(JobScore)))) == 1
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
        observations.close()


async def test_atomic_run_insert_collision_reuses_only_identical_binding(
    workflow_runtime,
):
    kernel, factory = workflow_runtime
    run_id = "10000000-0000-4000-8000-000000000001"
    inputs = {
        "job_ref": "job:first",
        "profile_ref": "profile:current",
        "event_ref": "event:one",
    }
    domain = {"domain_type": "job_posting", "domain_id": "job:first"}

    async def create():
        return await WorkflowKernel(factory).start_run(
            JOB_SCORE_V1, inputs, domain, "new", run_id=run_id
        )

    first, second = await asyncio.gather(create(), create())
    assert first.id == second.id == run_id
    with pytest.raises(ValueError, match="workflow_run_identity_conflict"):
        await kernel.start_run(
            JOB_SCORE_V1,
            {**inputs, "profile_ref": "profile:other"},
            domain,
            "new",
            run_id=run_id,
        )
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
        assert len(list(await session.scalars(select(WorkflowStepRecord)))) == 1
        assert len(list(await session.scalars(select(TaskAttemptRecord)))) == 1
        assert (await session.get(WorkflowRunRecord, run_id)).input_ref_json == inputs
