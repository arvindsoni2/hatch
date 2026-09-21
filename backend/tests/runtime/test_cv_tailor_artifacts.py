"""Artifact isolation contracts for the R6 CV Tailor runtime."""

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime_bindings.migration.cv_tailor import CVTailorRuntime
from app.runtime_bindings.tasks.cv_tailor import CVTailorInput, CVTailorOutput
from app.schemas.tailor import TailoredCVResult, TailoredExperience


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


async def test_shadow_cv_never_overwrites_visible_artifact() -> None:
    committed: list[str] = []

    async def commit(output: CVTailorOutput) -> str:
        committed.append(output.artifact_ref)
        return output.artifact_ref

    result = await CVTailorRuntime(
        produce=lambda _: _output(), commit_artifact=commit
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert committed == []


async def test_unsupported_claim_fails_before_artifact_commit() -> None:
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

    result = await CVTailorRuntime(
        produce=lambda _: output, commit_artifact=commit
    ).run(_request(), mode=RuntimeMode.NEW)

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert committed == []


async def test_new_artifact_failure_returns_safe_failure_without_partial_result() -> (
    None
):
    async def commit(_: CVTailorOutput) -> str:
        raise OSError("synthetic artifact failure")

    result = await CVTailorRuntime(
        produce=lambda _: _output(), commit_artifact=commit
    ).run(_request(), mode=RuntimeMode.NEW)

    assert result.code is ExecutionResultCode.PERMANENT_FAILURE
    assert result.output is None
    assert result.reason_code == "cv_tailor_artifact_failed"


async def test_repair_is_bounded_then_uses_fallback_output() -> None:
    invalid = _output().model_copy(
        update={"tailored_cv": TailoredCVResult(summary="", skills=[], experience=[])}
    )
    repairs: list[str] = []

    async def repair(_: CVTailorOutput) -> CVTailorOutput:
        repairs.append("repair")
        return invalid

    result = await CVTailorRuntime(
        produce=lambda _: invalid,
        repair=repair,
        fallback=lambda _: _output(),
    ).run(_request(), mode=RuntimeMode.SHADOW)

    assert result.code is ExecutionResultCode.SUCCESS
    assert result.reason_code == "cv_tailor_fallback"
    assert repairs == ["repair"]
