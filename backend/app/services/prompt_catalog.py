"""Stable metadata and risk contracts for every production AI prompt."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .writing_contracts import (
    COVER_LETTER_GENERATION_PROMPT,
    COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
    CV_TAILORING_PROMPT,
    PromptMetadata,
)

Risk = Literal["none", "low", "high"]


@dataclass(frozen=True)
class PromptContract:
    """Version and risk boundary for one production prompt."""

    metadata: PromptMetadata
    path: str
    family: str
    output_schema: str
    candidate_fact_risk: Risk
    employer_fact_risk: Risk
    numeric_fidelity_risk: Risk


def _metadata(prompt_id: str, task_name: str | None = None) -> PromptMetadata:
    return PromptMetadata(
        prompt_id=prompt_id,
        prompt_version="1.0.0",
        schema_version="1.0.0",
        task_name=task_name or prompt_id,
    )


def _contract(
    metadata: PromptMetadata,
    path: str,
    family: str,
    output_schema: str,
    *,
    candidate: Risk = "none",
    employer: Risk = "none",
    numeric: Risk = "none",
) -> PromptContract:
    return PromptContract(
        metadata=metadata,
        path=path,
        family=family,
        output_schema=output_schema,
        candidate_fact_risk=candidate,
        employer_fact_risk=employer,
        numeric_fidelity_risk=numeric,
    )


_CONTRACT_LIST = (
    _contract(
        _metadata("answer_evaluation"),
        "backend/app/prompts/answer_evaluation.j2",
        "coach_recommendations",
        "AnswerEvaluation",
        candidate="high",
        numeric="low",
    ),
    _contract(
        _metadata("ats_keywords"),
        "backend/app/prompts/ats_keywords.j2",
        "job_scoring",
        "ATSScoreResult",
        candidate="high",
        numeric="high",
    ),
    _contract(
        COVER_LETTER_GENERATION_PROMPT,
        "backend/app/prompts/cl_generation.j2",
        "candidate_document",
        "CoverLetterResult",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("company_research"),
        "backend/app/prompts/company_research.j2",
        "company_research",
        "CompanyResearchResponse",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("cv_parsing"),
        "backend/app/prompts/cv_parsing.j2",
        "cv_import",
        "CVParseResult",
        candidate="high",
        numeric="high",
    ),
    _contract(
        CV_TAILORING_PROMPT,
        "backend/app/prompts/cv_tailoring.j2",
        "candidate_document",
        "TailoredCVResult",
        candidate="high",
        employer="low",
        numeric="high",
    ),
    _contract(
        _metadata("follow_up_question"),
        "backend/app/prompts/follow_up.j2",
        "interview_questions",
        "FollowUpQuestion",
        candidate="low",
    ),
    _contract(
        _metadata("jd_analysis"),
        "backend/app/prompts/jd_analysis.j2",
        "job_extraction",
        "JDAnalysisResult",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("job_classification"),
        "backend/app/prompts/job_classification.j2",
        "job_search_ranking",
        "JobClassificationBatch",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("model_answer"),
        "backend/app/prompts/model_answer.j2",
        "interview_answers",
        "ModelAnswerResult",
        candidate="high",
        employer="low",
        numeric="high",
    ),
    _contract(
        _metadata("question_generation"),
        "backend/app/prompts/question_generation.j2",
        "interview_questions",
        "QuestionPresentationList",
        candidate="high",
        employer="high",
        numeric="low",
    ),
    _contract(
        _metadata("session_report"),
        "backend/app/prompts/session_report.j2",
        "coach_recommendations",
        "SessionFeedbackReport",
        candidate="high",
        employer="low",
        numeric="low",
    ),
    _contract(
        _metadata("speech_feedback"),
        "backend/app/prompts/speech_feedback.j2",
        "coach_recommendations",
        "SpeechFeedback",
        candidate="low",
        numeric="low",
    ),
    _contract(
        _metadata("summary_rewrite"),
        "backend/app/prompts/summary_rewrite.j2",
        "candidate_document",
        "SummaryRewriteResult",
        candidate="high",
        employer="low",
        numeric="high",
    ),
    _contract(
        _metadata("video_feedback"),
        "backend/app/prompts/video_feedback.j2",
        "coach_recommendations",
        "VideoFeedback",
        candidate="low",
        numeric="low",
    ),
    _contract(
        COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
        "backend/app/services/cl_generator.py",
        "candidate_document",
        "CoverLetterResult",
        candidate="high",
        numeric="high",
    ),
    _contract(
        _metadata("job_scoring_triage"),
        "backend/app/agents/scorer_agent.py",
        "job_scoring",
        "_TriageResult",
        candidate="high",
        employer="high",
        numeric="low",
    ),
    _contract(
        _metadata("job_scoring_detailed"),
        "backend/app/agents/scorer_agent.py",
        "job_scoring",
        "_ScoreResult",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("job_scoring_judge"),
        "backend/app/agents/scorer_agent.py",
        "job_scoring",
        "_ScoreResult",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("rubric_synthesis"),
        "backend/app/services/rubric_synthesiser.py",
        "coach_recommendations",
        "SessionRubric",
        candidate="high",
        numeric="low",
    ),
    _contract(
        _metadata("email_post_application"),
        "backend/app/services/email_generator.py",
        "candidate_document",
        "GeneratedEmail",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("email_post_interview_thankyou"),
        "backend/app/services/email_generator.py",
        "candidate_document",
        "GeneratedEmail",
        candidate="high",
        employer="high",
        numeric="high",
    ),
    _contract(
        _metadata("email_warm_reengagement"),
        "backend/app/services/email_generator.py",
        "candidate_document",
        "GeneratedEmail",
        candidate="high",
        employer="high",
        numeric="high",
    ),
)

PROMPT_CONTRACTS = {
    contract.metadata.prompt_id: contract
    for contract in _CONTRACT_LIST
}


def prompt_contract(prompt_id: str) -> PromptContract:
    """Return the contract for a known production prompt."""
    try:
        return PROMPT_CONTRACTS[prompt_id]
    except KeyError as exc:
        raise KeyError(f"Unknown production prompt ID: {prompt_id}") from exc


def prompt_metadata(prompt_id: str) -> PromptMetadata:
    """Return stable metadata for a known production prompt."""
    return prompt_contract(prompt_id).metadata
