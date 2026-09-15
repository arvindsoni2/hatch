"""Public source-event retry must not duplicate a runtime-owned score execution."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.scorer_agent import ScorerAgent
from app.agents.tools.event_bus import EventBus
from app.config import settings
from app.models.agent_event import AgentEvent
from app.models.cost_tracking import CostTracking
from app.models.job_score import JobScore
from app.runtime import RuntimeMode
from app.runtime.evaluation.models import ExecutionRecord
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.models import WorkflowRunRecord
from app.runtime.workflow import WorkflowKernel
from app.runtime_bindings.migration.job_score import DurableJobScoreRuntime
from job_score_test_support import install_profile, install_provider, job, profile


@pytest.mark.parametrize(
    "timing", ["after_runtime_commit", "before_source_ack", "after_source_ack"]
)
@pytest.mark.parametrize("relevant", [True, False])
async def test_public_retry_after_commit_error_never_reexecutes_score(
    db_session, client, monkeypatch, timing, relevant
):
    install_profile(monkeypatch, profile("llm"))
    install_provider(monkeypatch, [0.8, 0.8], triage_relevant=relevant)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    )
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    posting = job()
    db_session.add(posting)
    await db_session.commit()
    event_id = await scorer._bus.emit(
        "job_discovered", "scout", {"job_id": posting.id}, db_session
    )
    status_at_commit = None
    with monkeypatch.context() as fault:
        if timing == "after_runtime_commit":
            execute = DurableJobScoreRuntime.score_job

            async def interrupted_return(self, *args, **kwargs):
                nonlocal status_at_commit
                await execute(self, *args, **kwargs)
                async with factory.session_factory() as observer:
                    source = await observer.get(AgentEvent, event_id)
                    status_at_commit = source.status
                raise TimeoutError("SYNTHETIC_POST_COMMIT_CANARY")

            fault.setattr(DurableJobScoreRuntime, "score_job", interrupted_return)
        else:
            acknowledge = EventBus.mark_completed

            async def interrupted_ack(self, *args, **kwargs):
                if timing == "after_source_ack":
                    await acknowledge(self, *args, **kwargs)
                raise TimeoutError("SYNTHETIC_POST_COMMIT_CANARY")

            fault.setattr(EventBus, "mark_completed", interrupted_ack)
        outcome = await scorer.run(db_session)
    source = await db_session.get(AgentEvent, event_id, populate_existing=True)
    status_before_retry = source.status
    retry = await client.post(f"/api/events/{event_id}/retry")
    await scorer.run(db_session)
    # Count real durable execution/cost rows, not calls to the provider fake.
    assert len(list(await db_session.scalars(select(WorkflowRunRecord)))) == 1
    assert len(list(await db_session.scalars(select(ExecutionRecord)))) == 1
    assert len(list(await db_session.scalars(select(CostTracking)))) == (
        2 if relevant else 0
    )
    assert len(list(await db_session.scalars(select(JobScore)))) == int(relevant)
    assert len(
        list(
            await db_session.scalars(
                select(AgentEvent).where(AgentEvent.event_type == "job_scored")
            )
        )
    ) == int(relevant)
    assert status_before_retry == "completed"
    if timing == "after_runtime_commit":
        assert status_at_commit == "completed"
    assert outcome == {
        "scored": int(relevant),
        "skipped": int(not relevant),
        "errors": 0,
    }
    assert retry.status_code == 200
    assert retry.json()["status"] == "completed"
    await db_session.refresh(source)
    assert source.status == "completed"
    assert source.error_message is None


@pytest.mark.parametrize("timing", ["after_start", "after_claim", "terminal_failure"])
async def test_public_retry_cannot_escape_existing_runtime_lifecycle(
    db_session, client, monkeypatch, timing
):
    install_profile(monkeypatch, profile())
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    )
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    posting = job()
    if timing != "terminal_failure":
        db_session.add(posting)
        await db_session.commit()
    event_id = await scorer._bus.emit(
        "job_discovered", "scout", {"job_id": posting.id}, db_session
    )
    with monkeypatch.context() as fault:
        claim = WorkflowKernel.claim_run

        async def interrupted_claim(self, *args, **kwargs):
            if timing == "after_claim":
                await claim(self, *args, **kwargs)
            raise TimeoutError("SYNTHETIC_CLAIM_CANARY")

        if timing != "terminal_failure":
            fault.setattr(WorkflowKernel, "claim_run", interrupted_claim)
        assert await scorer.run(db_session) == {"scored": 0, "skipped": 0, "errors": 1}
    executions = list(await db_session.scalars(select(ExecutionRecord.id)))
    for _ in range(2):
        response = await client.post(f"/api/events/{event_id}/retry")
        assert response.status_code == 409
        assert response.json()["detail"] == "Event retry is owned by runtime"
    assert list(await db_session.scalars(select(ExecutionRecord.id))) == executions
    assert len(list(await db_session.scalars(select(WorkflowRunRecord)))) == 1
    assert not list(await db_session.scalars(select(CostTracking)))
    assert not list(await db_session.scalars(select(JobScore)))


@pytest.mark.parametrize("stale_status", ["failed", "pending"])
async def test_stale_source_state_reconciles_completed_run_without_new_work(
    db_session, client, monkeypatch, stale_status
):
    install_profile(monkeypatch, profile("llm"))
    install_provider(monkeypatch, [0.8, 0.8])
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    )
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    posting = job()
    db_session.add(posting)
    await db_session.commit()
    event_id = await scorer._bus.emit(
        "job_discovered", "scout", {"job_id": posting.id}, db_session
    )
    await scorer.run(db_session)
    source = await db_session.get(AgentEvent, event_id, populate_existing=True)
    source.status = stale_status
    source.error_message = "historical_job_score_runtime_failed"
    await db_session.commit()
    response = await client.post(f"/api/events/{event_id}/retry")
    await scorer.run(db_session)
    assert len(list(await db_session.scalars(select(WorkflowRunRecord)))) == 1
    assert len(list(await db_session.scalars(select(ExecutionRecord)))) == 1
    assert len(list(await db_session.scalars(select(CostTracking)))) == 2
    assert response.status_code in (200, 409)
    await db_session.refresh(source)
    assert source.status == "completed"
    assert source.error_message is None
