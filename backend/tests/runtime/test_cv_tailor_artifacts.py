"""Artifact isolation contracts for the R6 CV Tailor runtime."""

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime_bindings.migration.cv_tailor import DurableCVTailorRuntime
from app.runtime_bindings.tasks.cv_tailor import CVTailorInput, CVTailorOutput
from app.schemas.tailor import TailoredCVResult, TailoredExperience
from app.services.docx_cv_builder import DocxCVBuilder


def _request() -> CVTailorInput:
    return CVTailorInput(
        application_ref="application:synthetic-001", job_ref="job:synthetic-001"
    )


def _output() -> CVTailorOutput:
    return CVTailorOutput(
        tailored_cv=TailoredCVResult(
            summary="AWS engineer",
            skills=[{"category": "Cloud", "items": ["AWS"]}],
            experience=[
                TailoredExperience(
                    role="Engineer",
                    company="Example Ltd",
                    period="2020-2024",
                    achievements=["Delivered AWS platform migrations."],
                )
            ],
        ),
        artifact_ref="artifact:cv-001",
        artifact_bytes=100,
        source_claims=(
            "AWS engineer",
            "AWS",
            "Engineer",
            "Example Ltd",
            "2020-2024",
            "Delivered AWS platform migrations.",
        ),
    )


async def test_shadow_cv_never_overwrites_visible_artifact(workflow_runtime) -> None:
    committed: list[str] = []

    async def commit(output: CVTailorOutput) -> str:
        committed.append(output.artifact_ref)
        return output.artifact_ref

    output = _output()
    kernel, factory = workflow_runtime
    result = await DurableCVTailorRuntime(
        kernel, factory=factory, worker_id="shadow-artifact", job_description="AWS required",
        produce=lambda _: output,
        commit_artifact=commit,
        source_claims=output.source_claims,
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert committed == []


async def test_unsupported_claim_fails_before_artifact_commit(workflow_runtime) -> None:
    committed: list[str] = []

    async def commit(output: CVTailorOutput) -> str:
        committed.append(output.artifact_ref)
        return output.artifact_ref

    output = _output().model_copy(
        update={
            "tailored_cv": TailoredCVResult(
                summary="AWS engineer who invented 99% growth",
                skills=[{"category": "Cloud", "items": ["AWS"]}],
                experience=[
                    TailoredExperience(
                        role="Engineer",
                        company="Example Ltd",
                        period="2020-2024",
                        achievements=["Delivered AWS platform migrations."],
                    )
                ],
            )
        }
    )

    kernel, factory = workflow_runtime
    result = await DurableCVTailorRuntime(
        kernel, factory=factory, worker_id="unsupported-artifact", job_description="AWS required",
        produce=lambda _: output,
        commit_artifact=commit,
        source_claims=_output().source_claims,
    ).run(_request(), mode=RuntimeMode.NEW)

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert committed == []


async def test_new_artifact_failure_returns_safe_failure_without_partial_result(workflow_runtime) -> None:
    async def commit(_: CVTailorOutput) -> str:
        raise OSError("synthetic artifact failure")

    output = _output()
    kernel, factory = workflow_runtime
    result = await DurableCVTailorRuntime(
        kernel, factory=factory, worker_id="failed-artifact", job_description="AWS required",
        produce=lambda _: output,
        commit_artifact=commit,
        source_claims=output.source_claims,
    ).run(_request(), mode=RuntimeMode.NEW)

    # The gateway deliberately treats a crashing idempotent artifact adapter
    # as ambiguous so the durable reconciler, rather than a second writer,
    # owns recovery.
    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.output is None
    assert result.reason_code == "capability_exception_ambiguous"


async def test_repair_is_bounded_then_uses_fallback_output(workflow_runtime) -> None:
    invalid = _output().model_copy(
        update={"tailored_cv": TailoredCVResult(summary="", skills=[], experience=[])}
    )
    repairs: list[str] = []

    async def repair(_: CVTailorOutput) -> CVTailorOutput:
        repairs.append("repair")
        return invalid

    kernel, factory = workflow_runtime
    result = await DurableCVTailorRuntime(
        kernel, factory=factory, worker_id="repair-artifact", job_description="AWS required",
        produce=lambda _: invalid,
        repair=repair,
        fallback=lambda _: _output(),
        source_claims=_output().source_claims,
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert result.reason_code == "cv_tailor_fallback"
    assert repairs == ["repair"]


async def test_durable_shadow_persists_run_context_and_execution_without_artifact(
    workflow_runtime, monkeypatch
) -> None:
    from app.runtime.evaluation.models import ExecutionRecord
    from app.runtime.workflow.models import WorkflowRunRecord
    from sqlalchemy import select

    kernel, factory = workflow_runtime
    output = _output()
    committed: list[str] = []

    async def commit(value: CVTailorOutput) -> str:
        committed.append(value.artifact_ref)
        return value.artifact_ref

    monkeypatch.setattr(
        "app.runtime_bindings.context.profile.get_profile_dict", lambda: {"skills": []}
    )
    monkeypatch.setattr(
        "app.runtime_bindings.context.resume.get_resume_text", lambda: "synthetic"
    )
    result = await DurableCVTailorRuntime(
        kernel,
        factory=factory,
        worker_id="cv-test",
        produce=lambda _: output,
        source_claims=output.source_claims,
        commit_artifact=commit,
        job_description="AWS required",
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert committed == []
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
        assert len(list(await session.scalars(select(ExecutionRecord)))) == 1


def test_promotion_conflict_never_deletes_a_peer_final_artifact(tmp_path) -> None:
    staged = tmp_path / "staged.docx"
    final = tmp_path / "final.docx"
    staged.write_bytes(b"ours")
    final.write_bytes(b"peer")

    try:
        DocxCVBuilder.promote_staged(str(staged), str(final))
    except RuntimeError as exc:
        assert str(exc) == "cv_artifact_promotion_conflict"
    else:
        raise AssertionError("expected no-overwrite promotion conflict")

    assert final.read_bytes() == b"peer"
    assert staged.read_bytes() == b"ours"
