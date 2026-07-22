"""Stable metadata and risk contracts for every production AI prompt."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable, Literal

from .writing_contracts import (
    COVER_LETTER_GENERATION_PROMPT,
    COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
    CV_TAILORING_PROMPT,
    EvidenceItem,
    PromptMetadata,
    SHARED_FACTUALITY_CONTRACT,
    SHARED_NUMERIC_FIDELITY_CONTRACT,
    ValidationResult,
    normalize_evidence_text,
    validate_numeric_fidelity,
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


def _metadata(
    prompt_id: str,
    task_name: str | None = None,
    *,
    prompt_version: str = "1.0.0",
) -> PromptMetadata:
    return PromptMetadata(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
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
        _metadata("answer_evaluation", prompt_version="2.0.0"),
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
        _metadata("model_answer", prompt_version="2.0.0"),
        "backend/app/prompts/model_answer.j2",
        "interview_answers",
        "ModelAnswerResult",
        candidate="high",
        employer="low",
        numeric="high",
    ),
    _contract(
        _metadata("question_generation", prompt_version="2.0.0"),
        "backend/app/prompts/question_generation.j2",
        "interview_questions",
        "QuestionPresentationList",
        candidate="high",
        employer="high",
        numeric="low",
    ),
    _contract(
        _metadata("question_generation_repair"),
        "backend/app/prompts/question_generation_repair.j2",
        "interview_questions",
        "QuestionPresentationList",
        candidate="high",
        employer="high",
        numeric="low",
    ),
    _contract(
        _metadata("session_report", prompt_version="2.0.0"),
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
        _metadata("rubric_synthesis", prompt_version="2.0.0"),
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


def prompt_contract_block(prompt_id: str) -> str:
    """Render non-private version metadata for prompt assembly."""
    metadata = prompt_metadata(prompt_id)
    return "PROMPT METADATA:\n" + json.dumps(
        asdict(metadata),
        ensure_ascii=False,
        sort_keys=True,
    )


def candidate_claim_contract(prompt_id: str) -> str:
    """Render the candidate-evidence boundary for a high-risk prompt."""
    contract = prompt_contract(prompt_id)
    if contract.candidate_fact_risk != "high":
        raise ValueError(
            f"Prompt {prompt_id!r} is not cataloged as high candidate-fact risk"
        )
    return "\n\n".join(
        (
            prompt_contract_block(prompt_id),
            SHARED_FACTUALITY_CONTRACT,
            SHARED_NUMERIC_FIDELITY_CONTRACT,
            (
                "CANDIDATE CLAIM RULES:\n"
                "- Map each candidate-specific claim to an approved evidence ID.\n"
                "- Preserve numeric tokens exactly as supplied in approved evidence.\n"
                "- Do not infer dates, employers, credentials, tools, seniority, "
                "budgets, team sizes, outcomes, eligibility, or stakeholders.\n"
                "- If required evidence is unavailable, return review_required or "
                "the task's documented empty safe fallback."
            ),
        )
    )


def research_claim_contract(prompt_id: str) -> str:
    """Render the source boundary for a high-risk employer/research prompt."""
    contract = prompt_contract(prompt_id)
    if contract.employer_fact_risk != "high":
        raise ValueError(
            f"Prompt {prompt_id!r} is not cataloged as high employer-fact risk"
        )
    return "\n\n".join(
        (
            prompt_contract_block(prompt_id),
            (
                "RESEARCH FACT RULES:\n"
                "- Map every employer or research fact to a supplied source ID.\n"
                "- Preserve the retrieval timestamp for each source.\n"
                "- Include the fact date when the source supplies one.\n"
                "- Record a confidence or verification state for every fact.\n"
                "- Use verification state not_verified when sources do not support "
                "a claim; never fill a gap by invention.\n"
                "- Never blend employer or research facts into candidate history."
            ),
        )
    )


def source_contains(value: str, source: str) -> bool:
    """Return whether a normalized value is explicitly present in source text."""
    normalized_value = normalize_evidence_text(value).casefold()
    normalized_source = normalize_evidence_text(source).casefold()
    return bool(normalized_value) and normalized_value in normalized_source


def validate_candidate_output(
    candidate_prose: Iterable[str],
    ledger: Iterable[EvidenceItem],
    employer_context: Iterable[str] = (),
) -> ValidationResult:
    """Apply the shared numeric gate to candidate-facing generated prose."""
    return validate_numeric_fidelity(
        candidate_prose,
        ledger,
        employer_context,
    )
