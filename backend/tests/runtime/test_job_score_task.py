"""Task-contract tests for the R5 Job Scoring runtime binding."""

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionStrategy
from app.runtime.control import ConstraintSet
from app.runtime_bindings.migration.job_score import DurableJobScoreRuntime
from app.runtime.evaluation.models import ExecutionRecord
from sqlalchemy import select
from job_score_test_support import job, profile, install_profile, install_provider
from app.runtime_bindings.tasks.job_score import (
    JOB_SCORE_V1,
    JobScoreInput,
    JobScoreOutput,
)
import pytest


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


def test_job_score_contract_has_reference_input_and_legacy_durable_output_shape() -> (
    None
):
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


async def test_policy_excludes_cloud_and_runtime_uses_only_local_fallback(
    workflow_runtime, monkeypatch
):
    kernel, factory = workflow_runtime
    install_profile(monkeypatch, profile("llm"))
    install_provider(monkeypatch, [])
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
    runtime = DurableJobScoreRuntime(
        kernel,
        worker_id="scorer",
        factory=factory,
        security_policy=ConstraintSet(data_egress=False),
    )
    result = await runtime.score_job(
        JobScoreInput(
            job_ref=f"job:{posting.id}",
            profile_ref="profile:current",
            event_ref="event:synthetic",
        ),
        mode=RuntimeMode.SHADOW,
    )
    assert result.output.overall_score == 0.89
    async with factory.session_factory() as session:
        records = list(await session.scalars(select(ExecutionRecord)))
        assert len(records) == 2
        primary = next(row for row in records if row.execution_role == "primary")
        assert primary.result_class == "policy_denied"
        assert primary.input_tokens == 0
        assert primary.output_tokens == 0
        assert result.usage.model_id == "local-keyword"


@pytest.mark.parametrize("constraint", ["local_transport_egress", "triage_model"])
async def test_runtime_retains_policy_refusal_and_never_calls_excluded_transport(
    workflow_runtime, monkeypatch, constraint
):
    kernel, factory = workflow_runtime
    candidate = profile("llm")
    if constraint == "local_transport_egress":
        candidate.llm.provider = "llamacpp"
        policy = ConstraintSet(data_egress=False)
    else:
        policy = ConstraintSet(
            allowed_models=frozenset({"configured-primary", "local-keyword"})
        )
    install_profile(monkeypatch, candidate)
    calls = []

    def forbidden_model(*args):
        calls.append(args)
        raise AssertionError("excluded transport invoked")

    monkeypatch.setattr("app.agents.tools.llm_factory._build_model", forbidden_model)
    async with factory.session_factory() as session:
        posting = job()
        session.add(posting)
        await session.commit()
    runtime = DurableJobScoreRuntime(
        kernel, worker_id="scorer", factory=factory, security_policy=policy
    )
    result = await runtime.score_job(
        JobScoreInput(
            job_ref=f"job:{posting.id}",
            profile_ref="profile:current",
            event_ref="event:synthetic",
        ),
        mode=RuntimeMode.SHADOW,
    )
    assert result.output.overall_score == 0.89
    assert calls == []
    async with factory.session_factory() as session:
        records = list(await session.scalars(select(ExecutionRecord)))
        assert len(records) == 2
        primary = next(row for row in records if row.execution_role == "primary")
        assert primary.result_class == "policy_denied"
        assert primary.input_tokens == 0
