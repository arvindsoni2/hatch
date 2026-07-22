from pathlib import Path

from app.services.coach_contracts import CoachDiagnostic
from benchmarks.coach.production_adapter import StageExecution
from benchmarks.coach.scoring import score_execution
from benchmarks.coach.suite_loader import load_suite
from benchmarks.coach.validators import ValidationResult, validate_execution

ROOT = Path(__file__).resolve().parents[4]
SUITE = load_suite(ROOT / "backend/benchmarks/coach/fixtures/v1")


def _execution(scenario_id: str, output: dict, outcome: str = "completed") -> StageExecution:
    scenario = SUITE.scenario(scenario_id)
    diagnostic = CoachDiagnostic(
        stage=scenario.stage,  # type: ignore[arg-type]
        outcome=outcome,  # type: ignore[arg-type]
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=[],
        duration_ms=0,
    )
    return StageExecution(output, diagnostic, 0, 0)


def test_correct_expected_withholding_scores_one_hundred() -> None:
    scenario = SUITE.scenario("ma_02_insufficient_evidence")
    execution = _execution(
        scenario.scenario_id,
        {"model_answer": "", "star_breakdown": {}, "evidence_references": []},
        "withheld_insufficient_evidence",
    )
    score = score_execution(scenario, execution, validate_execution(scenario, execution))
    assert score.quality_score == "100.0"
    assert all(value is None for value in score.dimensions.values())


def test_blocking_gate_prevents_quality_score() -> None:
    scenario = SUITE.scenario("ma_01_supported_star")
    execution = _execution(scenario.scenario_id, {})
    validation = ValidationResult.from_codes(["coach_model_answer_schema_invalid"])
    assert score_execution(scenario, execution, validation).quality_score is None


def test_answer_evaluation_scores_exact_band_agreement_and_calibration() -> None:
    scenario = SUITE.scenario("ae_01_strong_answer")
    scores = {key: 8 for key in scenario.expected.score_ranges if key != "overall"}
    execution = _execution(
        scenario.scenario_id,
        {
            "evaluation_state": "completed",
            "scores": scores,
            "overall": 8.0,
            "evidence_references": ["dependency reviews"],
            "strengths": ["strong structure and specificity"],
            "improvements": [],
            "follow_up_question": None,
        },
    )
    score = score_execution(scenario, execution, validate_execution(scenario, execution))
    assert score.dimensions["dimension_band_agreement"] == "100.0"
    assert score.dimensions["overall_score_calibration"] == "100.0"


def test_question_diversity_is_na_for_one_question() -> None:
    scenario = SUITE.scenario("qg_01_requirement_coverage")
    execution = _execution(
        scenario.scenario_id,
        {
            "questions": [
                {
                    "text": "How would you manage delivery risk?",
                    "category": "Technical",
                    "difficulty": "medium",
                    "requirement_id": "REQ-01",
                }
            ]
        },
    )
    score = score_execution(scenario, execution, ValidationResult())
    assert score.dimensions["question_diversity"] is None


def test_company_research_formula_emits_all_weighted_dimensions() -> None:
    scenario = SUITE.scenario("cr_01_grounded_synthesis")
    execution = _execution(
        scenario.scenario_id,
        {
            "company_name": "Atlas Example Cloud",
            "description": "Workflow software for regulated service teams",
            "sector": "workflow software",
            "recent_news": ["event-driven integration"],
            "key_products": ["Atlas Flow"],
            "tech_stack_signals": ["workflow APIs"],
            "verification_state": "verified",
            "sources": [
                {"source_id": item}
                for item in scenario.scoring.expected_source_ids
            ],
        },
    )
    score = score_execution(scenario, execution, ValidationResult())
    assert set(score.dimensions) == {
        "source_factual_grounding",
        "verification_uncertainty",
        "role_company_relevance",
        "conciseness_schema_usability",
    }
    assert score.quality_score is not None


def test_rubric_report_and_drill_formulas_emit_quality_scores() -> None:
    rubric = SUITE.scenario("rb_01_score_immutability")
    rubric_dimensions = {
        key: {
            "score": value,
            "evidence": ["Introduced dependency reviews"],
            "drill": f"Practise {key} for 10 minutes",
        }
        for key, value in rubric.input["baseline_scores"].items()
    }
    rubric_score = score_execution(
        rubric,
        _execution(
            rubric.scenario_id,
            {
                "dimensions": rubric_dimensions,
                "focus_for_next_session": "communication then star structure",
            },
        ),
        ValidationResult(),
    )

    report = SUITE.scenario("sr_01_mixed_session_report")
    report_score = score_execution(
        report,
        _execution(
            report.scenario_id,
            {
                **report.input["authoritative_report"],
                "report_state": "completed",
                "executive_summary": "The session showed structure and a technical depth gap.",
                "strengths": ["structure"],
                "improvement_areas": ["technical_depth", "specificity"],
                "coaching_points": ["Practise technical depth for 15 minutes"],
                "practice_plan": [
                    {"activity": "Review one specific answer every day"}
                ],
            },
        ),
        ValidationResult(),
    )

    drill = SUITE.scenario("td_01_technical_drill")
    drill_score = score_execution(
        drill,
        _execution(
            drill.scenario_id,
            {
                "drills": [
                    {
                        "walkthrough": "Compare API rollback speed with safety and availability with consistency.",
                        "drill_prompt": "Explain one rollback criterion in 10 minutes.",
                    }
                ]
            },
        ),
        ValidationResult(),
    )

    assert rubric_score.quality_score is not None
    assert report_score.quality_score is not None
    assert drill_score.quality_score is not None
