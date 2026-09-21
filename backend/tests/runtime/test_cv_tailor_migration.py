"""Migration mode and bounded repair contracts for R6 CV tailoring."""

import pytest

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime_bindings.migration.cv_tailor import CVTailorMigrationDispatcher
from app.runtime_bindings.tasks.cv_tailor import CVTailorInput, CVTailorOutput
from app.schemas.tailor import TailoredCVResult, TailoredExperience
from app.config import Settings


def _request() -> CVTailorInput:
    return CVTailorInput(
        application_ref="application:synthetic-001", job_ref="job:synthetic-001"
    )


def _output(summary: str = "AWS engineer") -> CVTailorOutput:
    return CVTailorOutput(
        tailored_cv=TailoredCVResult(
            summary=summary,
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
            summary,
            "AWS",
            "Engineer",
            "Example Ltd",
            "2020-2024",
            "Delivered AWS platform migrations.",
        ),
    )


@pytest.mark.parametrize(
    ("mode", "authoritative_engine", "expected_calls"),
    [
        (RuntimeMode.LEGACY, "legacy", ["legacy"]),
        (RuntimeMode.SHADOW, "legacy", ["legacy", "runtime"]),
        (RuntimeMode.NEW, "runtime", ["runtime"]),
    ],
)
async def test_mode_has_exactly_one_visible_cv_writer(
    mode, authoritative_engine, expected_calls
) -> None:
    calls: list[str] = []

    async def legacy(_: CVTailorInput):
        calls.append("legacy")
        return _output()

    async def runtime(_: CVTailorInput):
        calls.append("runtime")
        return _output()

    result = await CVTailorMigrationDispatcher(
        mode=mode, legacy_generate=legacy, runtime_generate=runtime
    ).generate(_request())

    assert result.authoritative_engine == authoritative_engine
    assert result.visible_result == _output()
    assert calls == expected_calls


async def test_shadow_runtime_failure_preserves_legacy_result_and_never_promotes() -> (
    None
):
    async def legacy(_: CVTailorInput):
        return _output()

    async def runtime(_: CVTailorInput):
        raise TimeoutError("synthetic timeout")

    result = await CVTailorMigrationDispatcher(
        mode=RuntimeMode.SHADOW, legacy_generate=legacy, runtime_generate=runtime
    ).generate(_request())

    assert result.visible_result == _output()
    assert result.authoritative_engine == "legacy"
    assert result.shadow_reason_code == "runtime_failed"


async def test_new_validation_failure_does_not_fall_back_to_a_legacy_writer() -> None:
    calls: list[str] = []

    async def legacy(_: CVTailorInput):
        calls.append("legacy")
        return _output()

    async def runtime(_: CVTailorInput):
        calls.append("runtime")
        return ExecutionResultCode.VALIDATION_FAILURE

    result = await CVTailorMigrationDispatcher(
        mode=RuntimeMode.NEW, legacy_generate=legacy, runtime_generate=runtime
    ).generate(_request())

    assert result.visible_result is None
    assert result.authoritative_engine == "runtime"
    assert result.runtime_code is ExecutionResultCode.VALIDATION_FAILURE
    assert calls == ["runtime"]


def test_default_mode_remains_legacy_for_rollback() -> None:
    assert Settings(_env_file=None).HATCH_RUNTIME_CV_TAILOR_MODE is RuntimeMode.LEGACY
