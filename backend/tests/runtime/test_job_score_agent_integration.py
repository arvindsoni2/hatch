"""Actual agent, dispatcher, context, runtime and SQL projection integration."""

import json
from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.agents.scorer_agent import ScorerAgent
from app.config import settings
from app.runtime import RuntimeMode
from app.agents.tools.event_bus import EventBus
from app.models.job_score import JobScore
from app.models.cost_tracking import CostTracking
from app.models.agent_event import AgentEvent
from app.runtime.evaluation.models import (
    ExecutionRecord,
    ShadowComparisonRecord,
    ContextPackageRecord,
)
from app.runtime.workflow.models import (
    WorkflowRunRecord,
    WorkflowStepRecord,
    TaskAttemptRecord,
)
from app.runtime.workflow import WorkflowKernel
from app.runtime_bindings.migration.job_score import DurableJobScoreRuntime
from app.runtime_bindings.migration.facade import JobScoreClaimLost
from app.runtime_bindings.tasks.job_score import JobScoreInput
from job_score_test_support import job, profile, install_profile, install_provider


@pytest.mark.parametrize("mode", ["legacy", "shadow", "new"])
async def test_agent_modes_persist_one_score_and_real_runtime_lineage(
    workflow_runtime, monkeypatch, mode
):
    _, factory = workflow_runtime
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode(mode))
    monkeypatch.setattr("app.agents.scorer_agent.load_profile", lambda: profile())
    monkeypatch.setattr(
        "app.agents.tools.profile_loader.load_profile", lambda: profile()
    )
    monkeypatch.setattr(
        "app.services.resume_store.get_resume_text",
        lambda: "AWS Python Terraform synthetic resume",
    )
    if mode == "new":

        def forbidden_legacy(*args):
            raise AssertionError("NEW executed legacy scoring")

        monkeypatch.setattr("app.agents.scorer_agent.score_locally", forbidden_legacy)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        event_id = await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        assert len(scores) == 1
        assert scores[0].job_id == posting.id
        assert scores[0].overall_score == 0.89
        runs = list(await session.scalars(select(WorkflowRunRecord)))
        shadows = list(await session.scalars(select(ShadowComparisonRecord)))
        assert len(runs) == (0 if mode == "legacy" else 1)
        assert len(shadows) == (1 if mode == "shadow" else 0)
        if runs:
            run = runs[0]
            assert run.runtime_mode == mode
            assert run.domain_id == f"job:{posting.id}"
            assert run.input_ref_json["event_ref"] == f"event:{event_id}"
            attempt = await session.scalar(
                select(TaskAttemptRecord)
                .join(WorkflowStepRecord)
                .where(WorkflowStepRecord.workflow_run_id == run.id)
            )
            assert attempt.status == "succeeded", (
                str(shadows[0].metrics_json) if shadows else attempt.failure_code
            )
            package = await session.get(
                ContextPackageRecord, attempt.context_package_id
            )
            assert package is not None
            execution = await session.scalar(
                select(ExecutionRecord).where(
                    ExecutionRecord.task_attempt_id == attempt.id
                )
            )
            assert execution.model_id == "local-keyword"
            assert execution.model_version == "1"
            assert execution.input_tokens == 0
            assert execution.cost_usd == 0
            assert execution.latency_ms >= 0
            if shadows:
                shadow = shadows[0]
                assert shadow.runtime_execution_id == execution.id
                assert shadow.legacy_execution_ref == f"event:{event_id}"
                assert shadow.metrics_json["model_id"] == execution.model_id
                assert shadow.metrics_json["latency_ms"] >= execution.latency_ms
                assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(shadow.metrics_json)
            assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(package.items_json)
            assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(execution.metadata_json)


async def test_shadow_compares_independent_provider_result_and_measured_usage(
    workflow_runtime, monkeypatch, caplog
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    install_provider(monkeypatch, [0.9, 0.4])
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.SHADOW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        shadow = await session.scalar(select(ShadowComparisonRecord))
        assert len(scores) == 1
        assert scores[0].overall_score == 0.9
        assert shadow.metrics_json["score_delta"] == 0.5
        assert shadow.metrics_json["shortlist_agreement"] is False
        execution = await session.get(ExecutionRecord, shadow.runtime_execution_id)
        assert execution.model_id == "configured-primary"
        assert execution.model_version.startswith("config.")
        assert execution.input_tokens > 0
        assert execution.output_tokens > 0
        assert shadow.metrics_json["input_tokens"] == execution.input_tokens
        assert shadow.metrics_json["token_measurement"] == "estimated"
        assert [call["model_id"] for call in shadow.metrics_json["model_calls"]] == [
            "configured-triage",
            "configured-primary",
        ]
        assert all(
            call["model_version"].startswith("config.")
            for call in shadow.metrics_json["model_calls"]
        )
        assert (
            sum(call["input_tokens"] for call in shadow.metrics_json["model_calls"])
            == execution.input_tokens
        )
        assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(shadow.metrics_json)
        assert "SYNTHETIC_PRIVATE_CANARY" not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("SYNTHETIC_PRIVATE_CANARY"), ValueError("SYNTHETIC_PRIVATE_CANARY")],
)
@pytest.mark.parametrize("mode", [RuntimeMode.NEW, RuntimeMode.SHADOW])
async def test_new_provider_failure_uses_runtime_local_fallback_with_lineage(
    workflow_runtime, monkeypatch, failure, mode
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    install_provider(
        monkeypatch, [0.9, failure] if mode is RuntimeMode.SHADOW else [failure]
    )
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", mode)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        assert len(scores) == 1
        assert scores[0].overall_score == (0.9 if mode is RuntimeMode.SHADOW else 0.89)
        records = list(await session.scalars(select(ExecutionRecord)))
        assert len(records) == 2
        primary = next(r for r in records if r.execution_role == "primary")
        fallback = next(r for r in records if r.execution_role == "fallback")
        assert primary.result_class != "success"
        assert fallback.result_class == "success"
        assert fallback.parent_execution_id == primary.id
        assert fallback.task_attempt_id == primary.task_attempt_id
        assert fallback.model_id == "local-keyword"
        assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(primary.metadata_json)
        if mode is RuntimeMode.SHADOW:
            shadow = await session.scalar(select(ShadowComparisonRecord))
            assert shadow.runtime_execution_id == fallback.id
            assert shadow.metrics_json["reason_code"] == "local_fallback"
            assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(shadow.metrics_json)


async def test_shadow_context_failure_still_persists_comparison_and_one_visible_score(
    workflow_runtime, monkeypatch
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile())
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.SHADOW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job(description="")
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(JobScore)))) == 1
        shadow = await session.scalar(select(ShadowComparisonRecord))
        assert shadow.comparison_status == "runtime_failed"
        assert shadow.metrics_json["reason_code"] == "context_required_missing"
        assert (
            await session.get(ExecutionRecord, shadow.runtime_execution_id) is not None
        )


async def test_new_lost_claim_never_writes_a_legacy_fallback_projection(
    workflow_runtime, monkeypatch
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    replacement = None

    async def steal_expired_claim():
        nonlocal replacement
        async with factory.session_factory() as session:
            attempt = await session.scalar(select(TaskAttemptRecord))
        replacement = await WorkflowKernel(factory).reclaim(
            attempt.id, "replacement", datetime.utcnow() + timedelta(seconds=61)
        )
        assert replacement is not None

    install_provider(monkeypatch, [0.8], on_primary=steal_expired_claim)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        outcome = await scorer.run(session)
    async with factory.session_factory() as session:
        assert list(await session.scalars(select(JobScore))) == []
        assert outcome == {"scored": 0, "skipped": 0, "errors": 1}
        assert (
            await session.get(TaskAttemptRecord, replacement.task_attempt_id)
        ).current_claim_id == replacement.id


@pytest.mark.parametrize("mode", [RuntimeMode.SHADOW, RuntimeMode.NEW])
async def test_runtime_hybrid_preserves_batch_top_fraction_without_resume(
    workflow_runtime, monkeypatch, mode, caplog
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("hybrid"))
    monkeypatch.setattr("app.services.resume_store.get_resume_text", lambda: "")
    install_provider(monkeypatch, [0.8, 0.8] if mode is RuntimeMode.SHADOW else [0.8])
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", mode)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        for i in range(5):
            posting = job(
                title="Junior Warehouse Assistant SYNTHETIC_TITLE_CANARY",
                description=f"Synthetic packing vacancy {i}",
                location="Santiago",
            )
            session.add(posting)
            await session.commit()
            await scorer._bus.emit(
                "job_discovered", "scout", {"job_id": posting.id}, session
            )
        assert await scorer.run(session) == {"scored": 5, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(JobScore)))) == 5
        executions = list(await session.scalars(select(ExecutionRecord)))
        assert Counter(row.model_id for row in executions) == {
            "configured-primary": 1,
            "local-keyword": 4,
        }
    assert "SYNTHETIC_TITLE_CANARY" not in caplog.text


async def test_new_preserves_triage_endpoint_and_visible_cost_accounting(
    workflow_runtime, monkeypatch
):
    _, factory = workflow_runtime
    candidate = profile("llm")
    candidate.llm.provider = "llamacpp"
    candidate.llm.base_url = "http://localhost:8080/v1"
    candidate.llm.triage_base_url = "http://localhost:8081/v1"
    install_profile(monkeypatch, candidate)
    install_provider(monkeypatch, [0.8])
    from app.agents.tools import llm_factory

    build = llm_factory._build_model
    endpoints = []

    def capture(model_name, config):
        endpoints.append((model_name, config.base_url))
        return build(model_name, config)

    monkeypatch.setattr(llm_factory, "_build_model", capture)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    assert endpoints == [
        (candidate.llm.triage_model, candidate.llm.triage_base_url),
        (candidate.llm.primary_model, candidate.llm.base_url),
    ]
    async with factory.session_factory() as session:
        costs = list(await session.scalars(select(CostTracking)))
        assert {row.model for row in costs} == {
            candidate.llm.triage_model,
            candidate.llm.primary_model,
        }
        assert all(row.tokens_in > 0 and row.tokens_out > 0 for row in costs)
        event = await session.scalar(
            select(AgentEvent).where(AgentEvent.event_type == "job_scored")
        )
        payload = json.loads(event.payload)
        assert payload["model_used"] == candidate.llm.primary_model
        assert payload["duration_ms"] > 0


@pytest.mark.parametrize(
    "timing", ["after_start", "after_claim", "during_projection", "after_commit"]
)
async def test_new_exception_never_bypasses_runtime_fence_and_restart_projects_once(
    workflow_runtime, monkeypatch, timing
):
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile())
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
        event_id = await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        with monkeypatch.context() as failure:
            if timing in {"after_start", "after_claim"}:
                claim = WorkflowKernel.claim_run

                async def interrupted_claim(self, *args, **kwargs):
                    if timing == "after_claim":
                        await claim(self, *args, **kwargs)
                    raise TimeoutError("SYNTHETIC_EXCEPTION_CANARY")

                failure.setattr(WorkflowKernel, "claim_run", interrupted_claim)
            elif timing == "during_projection":
                write = ScorerAgent._write_visible_score

                async def interrupted_projection(self, *args, **kwargs):
                    await write(self, *args, **kwargs)
                    if kwargs.get("commit") is False:
                        raise RuntimeError("SYNTHETIC_EXCEPTION_CANARY")

                failure.setattr(
                    ScorerAgent, "_write_visible_score", interrupted_projection
                )
            else:
                score_job = DurableJobScoreRuntime.score_job

                async def interrupted_return(self, *args, **kwargs):
                    await score_job(self, *args, **kwargs)
                    raise RuntimeError("SYNTHETIC_EXCEPTION_CANARY")

                failure.setattr(DurableJobScoreRuntime, "score_job", interrupted_return)
            outcome = await scorer.run(session)
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        scored_events = list(
            await session.scalars(
                select(AgentEvent).where(AgentEvent.event_type == "job_scored")
            )
        )
        assert len(scores) == (1 if timing == "after_commit" else 0)
        assert len(scored_events) == (1 if timing == "after_commit" else 0)
        assert outcome == {"scored": 0, "skipped": 0, "errors": 1}
        run = await session.scalar(select(WorkflowRunRecord))
        attempt = await session.scalar(select(TaskAttemptRecord))
        assert (
            attempt.status
            == {
                "after_start": "pending",
                "after_claim": "running",
                "during_projection": "running",
                "after_commit": "succeeded",
            }[timing]
        )
        original_score_id = scores[0].id if scores else None
    recovery_time = datetime.utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(kernel.clock, "now", lambda: recovery_time)
    await kernel.reconcile(recovery_time)
    replacement = DurableJobScoreRuntime(kernel, worker_id="restarted", factory=factory)
    request = JobScoreInput(
        job_ref=f"job:{posting.id}",
        profile_ref="profile:current",
        event_ref=f"event:{event_id}",
    )

    async def project(uow, output, usage):
        await scorer._project_runtime_score(uow, request, output, usage)

    if timing != "after_commit":
        assert (
            await replacement.resume(run.id, projection=project)
        ).output.overall_score == 0.89
    with pytest.raises(JobScoreClaimLost, match="claim_unavailable"):
        await replacement.resume(run.id, projection=project)
    async with factory.session_factory() as session:
        scores = list(await session.scalars(select(JobScore)))
        scored_events = list(
            await session.scalars(
                select(AgentEvent).where(AgentEvent.event_type == "job_scored")
            )
        )
        assert len(scores) == len(scored_events) == 1
        assert scores[0].overall_score == 0.89
        if original_score_id:
            assert scores[0].id == original_score_id
        assert (await session.get(TaskAttemptRecord, attempt.id)).status == "succeeded"
        assert "SYNTHETIC_EXCEPTION_CANARY" not in scored_events[0].payload


async def test_new_event_references_canonical_score_without_copying_model_content(
    workflow_runtime, monkeypatch
):
    _, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    canary = "SYNTHETIC_CV_MODEL_ECHO /private/candidate.txt " * 1000
    install_provider(
        monkeypatch,
        [
            {
                "skill_match": 0.8,
                "experience_match": 0.8,
                "rate_match": 0.8,
                "location_match": 0.8,
                "overall_score": 0.8,
                "reasoning": canary,
                "fit_reasoning": canary,
                "strengths": [canary],
                "score_gaps": [canary],
                "keyword_matches": ["AWS"],
                "keyword_misses": [canary],
            }
        ],
    )
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    async with factory.session_factory() as session:
        posting = job(description=f"AWS Python Terraform. {canary}")
        session.add(posting)
        await session.commit()
        await scorer._bus.emit(
            "job_discovered", "scout", {"job_id": posting.id}, session
        )
        assert await scorer.run(session) == {"scored": 1, "skipped": 0, "errors": 0}
    async with factory.session_factory() as session:
        score = await session.scalar(select(JobScore))
        assert score.reasoning == score.fit_reasoning == canary
        assert score.strengths == score.score_gaps == score.keyword_misses == [canary]
        assert score.keyword_matches == ["AWS"]
        events = list(await session.scalars(select(AgentEvent)))
        assert all("SYNTHETIC_CV_MODEL_ECHO" not in event.payload for event in events)
        scored = next(event for event in events if event.event_type == "job_scored")
        assert len(scored.payload.encode()) < 2048
        payload = json.loads(scored.payload)
        assert payload["score_ref"] == f"job-score:{score.id}"
        assert payload["job_id"] == posting.id
        assert payload["score"] == 0.8
        assert (
            payload["skill_match"]
            == payload["experience_match"]
            == payload["rate_match"]
            == payload["location_match"]
            == 0.8
        )
        assert (
            not {
                "reasoning",
                "fit_reasoning",
                "strengths",
                "score_gaps",
                "keyword_matches",
                "keyword_misses",
            }
            & payload.keys()
        )
