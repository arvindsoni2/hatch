from __future__ import annotations

import inspect

from app.agents.scorer_agent import ScorerAgent
from app.services.cl_generator import CoverLetterGenerator
from app.services.company_researcher import CompanyResearchService
from app.services.coach_service import CoachService
from app.services.cv_tailor import CVTailor
from app.services.answer_evaluator import AnswerEvaluatorService
from app.services.ats_optimiser import ATSOptimiser
from app.services.job_classifier import JobClassifier
from app.services.question_generator import QuestionGeneratorService
from app.services.rubric_synthesiser import RubricSynthesiserService
from app.services.tailor_service import TailorService
from app.services.technical_drills import TechnicalDrillsService
from app.observability.attributes import COACH_OPERATION


def test_ai_entrypoints_declare_stable_workflow_names() -> None:
    assert CVTailor.tailor.__hatch_workflow__ == "cv_tailoring"
    assert CVTailor.tailor.__hatch_stage__ == "generate_initial"
    assert CoverLetterGenerator.generate.__hatch_workflow__ == "cover_letter_generation"
    assert CoverLetterGenerator.generate.__hatch_stage__ == "generate_initial"
    assert TailorService.generate_cv.__hatch_workflow__ == "cv_tailoring"
    assert (
        TailorService.generate_cover_letter.__hatch_workflow__
        == "cover_letter_generation"
    )
    assert ScorerAgent._score_with_llm.__hatch_workflow__ == "job_scoring"
    assert ScorerAgent._score_with_llm_judge.__hatch_workflow__ == "job_scoring"
    assert JobClassifier.classify_batch.__hatch_workflow__ == "job_discovery_import"
    assert CoachService.create_session.__hatch_workflow__ == "coach_generation"
    assert CoachService.submit_answer.__hatch_workflow__ == "coach_generation"
    assert CoachService.end_session.__hatch_workflow__ == "coach_generation"


def test_coach_model_boundary_declares_real_child_stage() -> None:
    assert QuestionGeneratorService.generate.__hatch_workflow__ == "coach_generation"
    assert QuestionGeneratorService.generate.__hatch_stage__ == "generate_initial"
    assert ATSOptimiser.score.__hatch_stage__ == "validate_output"
    assert CoverLetterGenerator.regenerate_paragraph.__hatch_stage__ == "repair_output"
    assert AnswerEvaluatorService.evaluate.__hatch_stage__ == "validate_output"
    assert RubricSynthesiserService.synthesise.__hatch_stage__ == "validate_output"
    assert CompanyResearchService.research.__hatch_stage__ == "prepare_input"
    assert (
        TechnicalDrillsService._build_single_drill.__hatch_stage__ == "generate_initial"
    )


def test_coach_entrypoints_declare_bounded_operations_and_top_stages() -> None:
    expected = {
        CoachService.create_session: ("session_create", "coach.session.create"),
        CoachService.submit_answer: ("answer_submit", "coach.answer.submit"),
        CoachService.end_session: ("session_end", "coach.session.end"),
        CoachService.plan_followup_session: (
            "followup_plan",
            "coach.followup.plan",
        ),
        CoachService.research_company: (
            "company_research",
            "coach.company_research",
        ),
    }

    for method, (operation, stage) in expected.items():
        assert method.__hatch_workflow__ == "coach_generation"
        assert method.__hatch_workflow_attributes__ == {
            COACH_OPERATION: operation,
        }
        assert method.__hatch_stage__ == stage


def test_coach_orchestrator_declares_required_child_stages_without_model_metrics() -> (
    None
):
    source = inspect.getsource(CoachService)
    required = {
        "coach.session.stub_persist",
        "coach.question_generation",
        "coach.model_answer.generate",
        "coach.questions.persist",
        "coach.technical_drills",
        "coach.session.activate",
        "coach.speech_metrics",
        "coach.video_metrics.validate",
        "coach.answer_evaluation",
        "coach.rubric_build",
        "coach.rubric_synthesis",
        "coach.recording.persist",
        "coach.recordings.load",
        "coach.session_rubric.aggregate",
        "coach.session_report",
        "coach.session.persist",
        "coach.parent_session.load",
        "coach.focus_areas.derive",
        "coach.followup_session.persist",
        "coach.followup_questions.copy",
    }

    for stage in required:
        assert f'"{stage}"' in source
    assert source.count("coach_stage_span(") >= len(required)
    assert 'stage="coach.company_research"' in source
    assert "record_model_call" not in source
