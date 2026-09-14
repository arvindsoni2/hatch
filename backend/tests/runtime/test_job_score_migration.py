"""Mode-dispatch contracts for the R5 Job Scoring migration."""

import pytest

from app.runtime import RuntimeMode
from app.runtime_bindings.migration.facade import JobScoreMigrationDispatcher
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _request() -> JobScoreInput:
    return JobScoreInput(
        job_ref="job:synthetic-001",
        profile_ref="profile:current",
        event_ref="event:synthetic-001",
    )


def _result(score: float = 0.8) -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=score,
        experience_match=score,
        rate_match=score,
        location_match=score,
        overall_score=score,
        reasoning="synthetic_reason",
        keyword_matches=("AWS",),
        keyword_misses=(),
        fit_reasoning="synthetic_fit_reason",
        strengths=("AWS",),
        score_gaps=(),
        scoring_method="local",
    )


@pytest.mark.parametrize(
    ("mode", "authority", "expected_calls"),
    [
        (RuntimeMode.LEGACY, "legacy", ["legacy"]),
        (RuntimeMode.SHADOW, "legacy", ["legacy", "runtime"]),
        (RuntimeMode.NEW, "runtime", ["runtime"]),
    ],
)
async def test_job_score_has_one_authoritative_writer(
    mode: RuntimeMode, authority: str, expected_calls: list[str]
) -> None:
    calls: list[str] = []

    async def legacy(_: JobScoreInput) -> JobScoreOutput:
        calls.append("legacy")
        return _result(0.8)

    async def runtime(_: JobScoreInput) -> JobScoreOutput:
        calls.append("runtime")
        return _result(0.8)

    result = await JobScoreMigrationDispatcher(
        mode=mode, legacy_score=legacy, runtime_score=runtime
    ).score_job(_request())

    assert result.authoritative_engine == authority
    assert result.visible_result == _result(0.8)
    assert calls == expected_calls


async def test_shadow_runtime_failure_never_changes_legacy_visible_result() -> None:
    async def legacy(_: JobScoreInput) -> JobScoreOutput:
        return _result(0.8)

    async def runtime(_: JobScoreInput) -> JobScoreOutput:
        raise TimeoutError("synthetic timeout")

    result = await JobScoreMigrationDispatcher(
        mode=RuntimeMode.SHADOW, legacy_score=legacy, runtime_score=runtime
    ).score_job(_request())

    assert result.authoritative_engine == "legacy"
    assert result.visible_result == _result(0.8)
    assert result.shadow_reason_code == "runtime_failed"


async def test_new_runtime_failure_falls_back_to_legacy_without_duplicate_writer() -> None:
    calls: list[str] = []

    async def legacy(_: JobScoreInput) -> JobScoreOutput:
        calls.append("legacy")
        return _result(0.8)

    async def runtime(_: JobScoreInput) -> JobScoreOutput:
        calls.append("runtime")
        raise TimeoutError("synthetic timeout")

    result = await JobScoreMigrationDispatcher(
        mode=RuntimeMode.NEW, legacy_score=legacy, runtime_score=runtime
    ).score_job(_request())

    assert result.authoritative_engine == "legacy_fallback"
    assert result.visible_result == _result(0.8)
    assert calls == ["runtime", "legacy"]
