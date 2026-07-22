from pathlib import Path

from app.services.coach_contracts import CoachDiagnostic
from benchmarks.coach.production_adapter import StageExecution
from benchmarks.coach.suite_loader import load_suite
from benchmarks.coach.validators import validate_execution

ROOT = Path(__file__).resolve().parents[4]
SUITE = load_suite(ROOT / "backend/benchmarks/coach/fixtures/v1")


def _execution(scenario_id: str, output: dict, *, gates: list[str] | None = None) -> StageExecution:
    scenario = SUITE.scenario(scenario_id)
    outcome = "completed"
    if scenario_id == "ma_02_insufficient_evidence":
        outcome = "withheld_insufficient_evidence"
    diagnostic = CoachDiagnostic(
        stage=scenario.stage,  # type: ignore[arg-type]
        outcome=outcome,  # type: ignore[arg-type]
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=gates or [],  # type: ignore[arg-type]
        duration_ms=0,
    )
    return StageExecution(output, diagnostic, 0, 0)


def test_expected_withholding_passes_contract() -> None:
    scenario = SUITE.scenario("ma_02_insufficient_evidence")
    result = validate_execution(
        scenario,
        _execution(
            scenario.scenario_id,
            {"model_answer": "", "star_breakdown": {}, "evidence_references": []},
        ),
    )
    assert result.eligible


def test_completed_model_answer_rejects_unknown_evidence_id() -> None:
    scenario = SUITE.scenario("ma_01_supported_star")
    result = validate_execution(
        scenario,
        _execution(
            scenario.scenario_id,
            {
                "model_answer": "answer",
                "star_breakdown": {key: key for key in ("situation", "task", "action", "result")},
                "evidence_references": ["unknown"],
            },
        ),
    )
    assert "coach_model_answer_unknown_evidence_id" in result.blocking_codes


def test_unavailable_evaluation_with_numeric_score_is_blocked() -> None:
    scenario = SUITE.scenario("ae_h01_provider_unavailable")
    result = validate_execution(
        scenario,
        _execution(
            scenario.scenario_id,
            {"evaluation_state": "unavailable", "scores": {"relevance": 5}, "overall": 5},
        ),
    )
    assert "coach_evaluation_fallback_unclassified" in result.blocking_codes


def test_report_score_mutation_is_a_blocking_gate() -> None:
    scenario = SUITE.scenario("sr_01_mixed_session_report")
    output = dict(scenario.input["authoritative_report"])
    output.update({"report_state": "completed", "overall_score": 9.9})
    result = validate_execution(scenario, _execution(scenario.scenario_id, output))
    assert "coach_report_score_mutation" in result.blocking_codes


def test_safety_gate_remains_blocking_after_production_correction() -> None:
    scenario = SUITE.scenario("qg_02_injection_resistance")
    result = validate_execution(
        scenario,
        _execution(scenario.scenario_id, {"questions": []}, gates=["coach_question_prompt_injection_followed"]),
    )
    assert "coach_question_prompt_injection_followed" in result.blocking_codes


def test_company_research_rejects_unknown_source_id() -> None:
    scenario = SUITE.scenario("cr_01_grounded_synthesis")
    result = validate_execution(
        scenario,
        _execution(
            scenario.scenario_id,
            {
                "verification_state": "verified",
                "sources": [{"source_id": "SRC-UNKNOWN"}],
            },
        ),
    )
    assert "coach_stage_failed" in result.blocking_codes


def test_rubric_score_mutation_is_a_blocking_gate() -> None:
    scenario = SUITE.scenario("rb_01_score_immutability")
    dimensions = {
        key: {"score": score, "evidence": [], "drill": "Practise for 10 minutes"}
        for key, score in scenario.input["baseline_scores"].items()
    }
    dimensions["relevance"]["score"] = 1
    result = validate_execution(
        scenario,
        _execution(
            scenario.scenario_id,
            {"dimensions": dimensions, "focus_for_next_session": "communication"},
        ),
    )
    assert "coach_rubric_score_mutation" in result.blocking_codes
