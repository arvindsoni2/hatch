"""Live durable mode and rollback contracts for R6 CV tailoring."""

from sqlalchemy import select

from app.config import Settings
from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation.models import ExecutionRecord
from app.runtime.workflow.models import TaskAttemptRecord, WorkflowRunRecord
from app.runtime_bindings.migration.cv_tailor import DurableCVTailorRuntime
from app.runtime_bindings.tasks.cv_tailor import CVTailorInput, CVTailorOutput
from app.schemas.tailor import TailoredCVResult, TailoredExperience


def _request() -> CVTailorInput:
    return CVTailorInput(
        application_ref="application:synthetic-002", job_ref="job:synthetic-002"
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
        artifact_ref="artifact:cv-002",
        artifact_bytes=100,
    )


async def test_new_mode_has_durable_run_attempt_generation_and_artifact_lineage(
    workflow_runtime,
) -> None:
    kernel, factory = workflow_runtime
    committed: list[str] = []

    async def commit(_: CVTailorOutput) -> str:
        committed.append("commit")
        return "artifact:committed-002"

    result = await DurableCVTailorRuntime(
        kernel,
        factory=factory,
        worker_id="new-live",
        produce=lambda _: _output(),
        source_claims=("AWS engineer", "Delivered AWS platform migrations."),
        job_description="AWS required",
        commit_artifact=commit,
    ).run(_request(), mode=RuntimeMode.NEW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert committed == ["commit"]
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 1
        assert len(list(await session.scalars(select(TaskAttemptRecord)))) == 1
        assert len(list(await session.scalars(select(ExecutionRecord)))) == 2


async def test_shadow_mode_records_durable_evaluation_but_cannot_commit(
    workflow_runtime,
) -> None:
    kernel, factory = workflow_runtime
    committed: list[str] = []

    async def commit(_: CVTailorOutput) -> str:
        committed.append("unexpected")
        return "artifact:unexpected"

    result = await DurableCVTailorRuntime(
        kernel,
        factory=factory,
        worker_id="shadow-live",
        produce=lambda _: _output(),
        source_claims=("AWS engineer", "Delivered AWS platform migrations."),
        job_description="AWS required",
        commit_artifact=commit,
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert committed == []
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(ExecutionRecord)))) == 1


async def test_request_identity_allows_repeat_generation_without_filename_reuse(
    workflow_runtime,
) -> None:
    kernel, factory = workflow_runtime
    commits: list[str] = []

    async def commit(_: CVTailorOutput) -> str:
        commits.append("commit")
        return f"artifact:repeat-{len(commits)}"

    runtime = DurableCVTailorRuntime(
        kernel,
        factory=factory,
        worker_id="repeat-live",
        produce=lambda _: _output(),
        source_claims=("AWS engineer", "Delivered AWS platform migrations."),
        job_description="AWS required",
        commit_artifact=commit,
    )
    for request_ref in ("request:repeat-1", "request:repeat-2"):
        await runtime.run(
            _request().model_copy(update={"request_ref": request_ref}),
            mode=RuntimeMode.NEW,
        )

    assert commits == ["commit", "commit"]
    async with factory.session_factory() as session:
        assert len(list(await session.scalars(select(WorkflowRunRecord)))) == 2


def test_default_mode_remains_legacy_for_rollback() -> None:
    assert Settings(_env_file=None).HATCH_RUNTIME_CV_TAILOR_MODE is RuntimeMode.LEGACY
