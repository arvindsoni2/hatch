"""Synthetic R2 gate measurements; this suite never changes the production mode."""

from statistics import mean

from app.runtime import RuntimeMode
from app.runtime_bindings.migration.facade import JobScoreMigrationDispatcher
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _output(score: float) -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=score,
        experience_match=score,
        rate_match=score,
        location_match=score,
        overall_score=score,
        reasoning="synthetic_reason",
        keyword_matches=(),
        keyword_misses=(),
        fit_reasoning=None,
        strengths=(),
        score_gaps=(),
        scoring_method="local",
    )


async def test_r2_synthetic_job_score_gate_is_measured_without_promoting_new(
    runtime_fixture,
) -> None:
    cases = runtime_fixture("job_score_r2_cases.json")
    threshold = 0.75
    assert [case["cohort"] for case in cases].count("strong_fit") == 20
    assert [case["cohort"] for case in cases].count("borderline") == 15
    assert [case["cohort"] for case in cases].count("poor_fit") == 15

    legacy_decisions: list[bool] = []
    new_decisions: list[bool] = []
    expected_decisions: list[bool] = []
    deltas: list[float] = []
    legacy_latencies: list[int] = []
    new_latencies: list[int] = []
    legacy_costs: list[int] = []
    new_costs: list[int] = []
    legacy_tokens: list[int] = []
    new_tokens: list[int] = []

    for case in cases:
        request = JobScoreInput(
            job_ref=f"job:{case['id']}",
            profile_ref="profile:synthetic",
            event_ref=f"event:{case['id']}",
        )

        async def legacy(_: JobScoreInput, score=case["legacy_score"]) -> JobScoreOutput:
            return _output(score)

        async def runtime(_: JobScoreInput, score=case["new_score"]) -> JobScoreOutput:
            return _output(score)

        legacy_result = await JobScoreMigrationDispatcher(
            mode=RuntimeMode.LEGACY, legacy_score=legacy, runtime_score=runtime
        ).score_job(request)
        new_result = await JobScoreMigrationDispatcher(
            mode=RuntimeMode.NEW, legacy_score=legacy, runtime_score=runtime
        ).score_job(request)
        assert legacy_result.authoritative_engine == "legacy"
        assert new_result.authoritative_engine == "runtime"
        assert 0 <= new_result.visible_result.overall_score <= 1

        legacy_decisions.append(legacy_result.visible_result.overall_score >= threshold)
        new_decisions.append(new_result.visible_result.overall_score >= threshold)
        expected_decisions.append(case["expected_shortlist"])
        deltas.append(
            abs(
                new_result.visible_result.overall_score
                - legacy_result.visible_result.overall_score
            )
        )
        legacy_latencies.append(case["legacy_latency_ms"])
        new_latencies.append(case["new_latency_ms"])
        legacy_costs.append(case["legacy_cost_microusd"])
        new_costs.append(case["new_cost_microusd"])
        legacy_tokens.append(case["legacy_tokens"])
        new_tokens.append(case["new_tokens"])

    legacy_accuracy = sum(a == b for a, b in zip(legacy_decisions, expected_decisions)) / len(cases)
    new_accuracy = sum(a == b for a, b in zip(new_decisions, expected_decisions)) / len(cases)
    agreement = sum(a == b for a, b in zip(legacy_decisions, new_decisions)) / len(cases)
    delta_within_tolerance = sum(delta <= 0.10 for delta in deltas) / len(cases)

    assert legacy_accuracy == 1.0
    assert new_accuracy >= 0.92
    assert new_accuracy >= legacy_accuracy - 0.02
    assert agreement >= 0.95
    assert delta_within_tolerance >= 0.90
    assert mean(new_latencies) <= 1.20 * mean(legacy_latencies)
    assert max(new_latencies) <= 1.25 * max(legacy_latencies)
    assert mean(new_costs) <= 1.15 * mean(legacy_costs)
    assert max(new_tokens) <= 1.25 * max(legacy_tokens)
