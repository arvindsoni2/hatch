from types import SimpleNamespace

from app.schemas.profile import OutcomeLearningConfig
from app.services.outcome_learning_service import calculate_for_features


def _row(positive: bool, source: str, weight: float = 1.0) -> dict:
    snapshot = SimpleNamespace(
        source=source,
        role_family="delivery manager",
        seniority="senior",
        working_pattern="hybrid",
        employment_type="contract",
        freshness_bucket="0_3_days",
    )
    return {"positive": positive, "weight": weight, "snapshot": snapshot}


def test_no_adjustment_below_minimum() -> None:
    config = OutcomeLearningConfig(minimum_total_applications=5, minimum_segment_size=3)
    result = calculate_for_features(0.72, {"source": "direct"}, [_row(True, "direct")], config)
    assert result["opportunity_score"] == 0.72
    assert result["outcome_adjustment"] == 0
    assert result["confidence"] == "insufficient"


def test_calculation_is_bounded_deterministic_and_explained() -> None:
    config = OutcomeLearningConfig(
        minimum_total_applications=5,
        minimum_segment_size=3,
        maximum_score_adjustment=0.10,
        maximum_signal_adjustment=0.04,
        enabled_signals=["source"],
    )
    rows = [_row(True, "direct") for _ in range(5)] + [_row(False, "board") for _ in range(5)]
    first = calculate_for_features(0.97, {"source": "direct"}, rows, config)
    second = calculate_for_features(0.97, {"source": "direct"}, rows, config)
    assert first == second
    assert first["opportunity_score"] <= 1.0
    assert 0 < first["outcome_adjustment"] <= 0.04
    assert first["reasons"][0]["sample_size"] == 5


def test_disabled_signal_produces_no_adjustment() -> None:
    config = OutcomeLearningConfig(minimum_total_applications=5, minimum_segment_size=3, enabled_signals=[])
    rows = [_row(True, "direct") for _ in range(5)]
    result = calculate_for_features(0.5, {"source": "direct"}, rows, config)
    assert result["outcome_adjustment"] == 0
    assert result["signal_contributions"] == {}
