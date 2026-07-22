from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.coach.contracts import (
    CoachScenario,
    CoachSuite,
    FixtureFile,
    FractionMetric,
    ScenarioExpected,
    ScenarioScoring,
)
from benchmarks.contracts import ModelSpec


def _scenario_payload() -> dict[str, object]:
    return {
        "scenario_id": "ae_01_strong_answer",
        "stage": "answer_evaluation",
        "description": "Strong grounded STAR answer",
        "qualification_scope": "model_capability",
        "input": {"transcript": "A synthetic answer."},
        "expected": {"outcome": "completed"},
        "scoring": {},
        "quality_dimensions": ["dimension_band_agreement"],
        "acceptance_smoke": True,
    }


def test_scenario_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CoachScenario.model_validate({**_scenario_payload(), "unknown": True})


def test_scenario_uses_strict_nested_contracts() -> None:
    payload = _scenario_payload()
    payload["expected"] = {"outcome": "completed", "surprise": True}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CoachScenario.model_validate(payload)


def test_forced_failure_requires_harness_contract_scope() -> None:
    with pytest.raises(ValidationError, match="forced failures must be harness_contract"):
        CoachScenario.model_validate(
            {**_scenario_payload(), "forced_failure": "provider_unavailable"}
        )


def test_harness_contract_accepts_declared_forced_failure() -> None:
    scenario = CoachScenario.model_validate(
        {
            **_scenario_payload(),
            "scenario_id": "ae_h01_provider_unavailable",
            "qualification_scope": "harness_contract",
            "forced_failure": "provider_unavailable",
        }
    )
    assert scenario.forced_failure == "provider_unavailable"


def test_fraction_metric_requires_consistent_zero_denominator() -> None:
    metric = FractionMetric(numerator=0, denominator=0, exact=None, display="N/A")
    assert metric.exact is None
    with pytest.raises(ValidationError, match="zero denominator"):
        FractionMetric(numerator=0, denominator=0, exact="0", display="0.0")


def test_model_spec_still_enforces_loopback_endpoint() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        ModelSpec(
            id="remote",
            runtime="ollama",
            model="remote/model",
            endpoint="https://models.example.com",
            context_size=8192,
        )


def test_suite_rejects_duplicate_scenario_ids() -> None:
    scenario = CoachScenario.model_validate(_scenario_payload())
    model = ModelSpec(
        id="qwen35-4b",
        runtime="ollama",
        model="qwen3.5:4b",
        endpoint="http://127.0.0.1:11434",
        context_size=32768,
    )
    with pytest.raises(ValidationError, match="scenario ids must be unique"):
        CoachSuite(
            suite_id="coach-v1",
            version="1",
            files=[FixtureFile(path=Path("models.json"), sha256="a" * 64)],
            models=[model],
            scenarios=[scenario, scenario],
        )


def test_expected_and_scoring_defaults_are_explicit() -> None:
    assert ScenarioExpected(outcome="completed").required_evidence_ids == []
    assert ScenarioScoring().banned_generic_phrases == []
