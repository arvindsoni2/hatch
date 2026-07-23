from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.coach.production_adapter import (
    CoachProductionAdapter,
    HarnessFailureClient,
    ScenarioContext,
)
from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
V1_SUITE = ROOT / "backend" / "benchmarks" / "coach" / "fixtures" / "v1"


@pytest.mark.asyncio
async def test_ae_h01_preserves_production_unavailable_no_score_contract() -> None:
    suite = load_suite(V1_SUITE)
    result = await CoachProductionAdapter().execute(
        suite.scenario("ae_h01_provider_unavailable"),
        HarnessFailureClient("provider_unavailable"),
        ScenarioContext.from_suite(suite),
    )

    assert result.output["evaluation_state"] == "unavailable"
    assert result.output["scores"] == {}
    assert result.output["overall"] is None
    assert result.gate_codes == ["coach_evaluation_provider_unavailable"]


@pytest.mark.asyncio
async def test_ae_h02_exhausts_production_parse_path() -> None:
    suite = load_suite(V1_SUITE)
    result = await CoachProductionAdapter().execute(
        suite.scenario("ae_h02_malformed_output"),
        HarnessFailureClient("malformed_output"),
        ScenarioContext.from_suite(suite),
    )

    assert result.output["evaluation_state"] == "invalid"
    assert result.output["scores"] == {}
    assert result.output["overall"] is None
    assert result.provider_attempt_count == 3
    assert result.gate_codes == ["coach_evaluation_schema_invalid"]


@pytest.mark.asyncio
async def test_sr_02_returns_production_fallback_with_authoritative_values() -> None:
    suite = load_suite(V1_SUITE)
    scenario = suite.scenario("sr_02_provider_fallback")
    result = await CoachProductionAdapter().execute(
        scenario,
        HarnessFailureClient("provider_unavailable"),
        ScenarioContext.from_suite(suite),
    )

    authoritative = scenario.input["authoritative_report"]
    assert result.output["report_state"] == "fallback"
    assert result.output["overall_score"] == authoritative["overall_score"]
    assert result.output["category_scores"] == authoritative["category_scores"]
    assert result.output["question_count_total"] == authoritative["question_count_total"]
    assert result.gate_codes == ["coach_report_provider_unavailable"]


def test_harness_failure_client_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unsupported harness failure mode"):
        HarnessFailureClient("random_failure")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_forced_failure_scenario_rejects_mismatched_harness_mode() -> None:
    suite = load_suite(V1_SUITE)
    with pytest.raises(ValueError, match="does not match scenario"):
        await CoachProductionAdapter().execute(
            suite.scenario("ae_h01_provider_unavailable"),
            HarnessFailureClient("malformed_output"),
            ScenarioContext.from_suite(suite),
        )
