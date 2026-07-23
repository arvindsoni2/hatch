from benchmarks.coach.contracts import CapabilityResult
from benchmarks.coach.scoring import rank_models


def _capability(
    model_id: str,
    *,
    classification: str = "coach_capable",
    safety: str = "1",
    hard: str = "1",
    quality: str = "90",
    calibration: str = "90",
    variance: str = "2",
    repair: str = "0.1",
    latency: str = "100",
) -> CapabilityResult:
    return CapabilityResult(
        model_id=model_id,
        classification=classification,
        ranking_metrics={
            "safety_critical_gate_pass_rate": safety,
            "core_hard_gate_pass_rate": hard,
            "median_normalised_core_quality": quality,
            "answer_evaluation_calibration": calibration,
            "quality_variance": variance,
            "question_generation_repair_rate": repair,
            "median_total_core_latency_ms": latency,
        },
    )


def test_ranking_uses_classification_then_locked_lexicographic_keys() -> None:
    capable = _capability("z-capable", quality="80")
    degraded = _capability(
        "a-degraded",
        classification="coach_capable_with_optional_degradation",
        quality="100",
    )
    unsafe = _capability("unsafe", safety="0.9", quality="100")
    ranked = rank_models([degraded, unsafe, capable])
    assert [item.model_id for item in ranked] == [
        "z-capable",
        "unsafe",
        "a-degraded",
    ]
    assert [item.rank for item in ranked] == [1, 2, 3]


def test_lower_variance_repair_latency_then_model_id_win_ties() -> None:
    values = [
        _capability("d", variance="3"),
        _capability("c", repair="0.2"),
        _capability("b", latency="200"),
        _capability("a"),
    ]
    assert [item.model_id for item in rank_models(values)] == ["a", "b", "c", "d"]


def test_ineligible_models_are_excluded() -> None:
    ranked = rank_models(
        [
            _capability("good"),
            _capability("bad", classification="not_coach_capable"),
            _capability("unknown", classification="inconclusive"),
        ]
    )
    assert [item.model_id for item in ranked] == ["good"]
