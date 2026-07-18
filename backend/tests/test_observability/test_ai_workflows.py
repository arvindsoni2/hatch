from __future__ import annotations

from app.agents.scorer_agent import ScorerAgent
from app.services.cl_generator import CoverLetterGenerator
from app.services.coach_service import CoachService
from app.services.cv_tailor import CVTailor
from app.services.answer_evaluator import AnswerEvaluatorService
from app.services.ats_optimiser import ATSOptimiser
from app.services.jd_analyser import JDAnalyser
from app.services.job_classifier import JobClassifier
from app.services.question_generator import QuestionGeneratorService
from app.services.rubric_synthesiser import RubricSynthesiserService
from app.services.tailor_service import TailorService


def test_ai_entrypoints_declare_stable_workflow_names() -> None:
    assert CVTailor.tailor.__hatch_workflow__ == "cv_tailoring"
    assert CVTailor.tailor.__hatch_stage__ == "generate_initial"
    assert (
        CoverLetterGenerator.generate.__hatch_workflow__
        == "cover_letter_generation"
    )
    assert CoverLetterGenerator.generate.__hatch_stage__ == "generate_initial"
    assert TailorService.generate_cv.__hatch_workflow__ == "cv_tailoring"
    assert (
        TailorService.generate_cover_letter.__hatch_workflow__
        == "cover_letter_generation"
    )
    assert ScorerAgent._score_with_llm.__hatch_workflow__ == "job_scoring"
    assert (
        ScorerAgent._score_with_llm_judge.__hatch_workflow__
        == "job_scoring"
    )
    assert (
        JobClassifier.classify_batch.__hatch_workflow__
        == "job_discovery_import"
    )
    assert CoachService.create_session.__hatch_workflow__ == "coach_generation"
    assert CoachService.submit_answer.__hatch_workflow__ == "coach_generation"
    assert CoachService.end_session.__hatch_workflow__ == "coach_generation"


def test_coach_model_boundary_declares_real_child_stage() -> None:
    assert (
        QuestionGeneratorService.generate.__hatch_workflow__
        == "coach_generation"
    )
    assert (
        QuestionGeneratorService.generate.__hatch_stage__
        == "generate_initial"
    )
    assert JDAnalyser.analyse.__hatch_stage__ == "prepare_input"
    assert ATSOptimiser.score.__hatch_stage__ == "validate_output"
    assert (
        CoverLetterGenerator.regenerate_paragraph.__hatch_stage__
        == "repair_output"
    )
    assert AnswerEvaluatorService.evaluate.__hatch_stage__ == "validate_output"
    assert RubricSynthesiserService.synthesise.__hatch_stage__ == "validate_output"
